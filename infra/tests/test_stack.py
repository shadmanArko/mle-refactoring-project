"""The template must have the security and cost properties the docs promise."""

import json

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template
from kc_house_infra.stack import Config, KcHouseStack


def build(**overrides) -> Template:
    app = cdk.App()
    stack = KcHouseStack(app, "Test", config=Config(**overrides))
    return Template.from_stack(stack)


@pytest.fixture(scope="module")
def rds() -> Template:
    return build(database="rds")


@pytest.fixture(scope="module")
def bare() -> Template:
    return build(database="none")


def function_properties(template: Template) -> dict:
    functions = template.find_resources(
        "AWS::Lambda::Function", {"Properties": {"PackageType": "Image"}}
    )
    assert len(functions) == 1
    return next(iter(functions.values()))["Properties"]


# --- the function ----------------------------------------------------------------


def test_function_is_a_container_image_on_arm(rds):
    properties = function_properties(rds)

    assert properties["Architectures"] == ["arm64"]
    assert properties["PackageType"] == "Image"
    assert properties["MemorySize"] == 2048
    assert properties["Timeout"] == 30


def test_the_image_is_built_from_the_lambda_target_for_arm(tmp_path):
    app = cdk.App(outdir=str(tmp_path))
    stack = KcHouseStack(app, "Test", config=Config(git_sha="abc123"))

    app.synth()

    manifest = json.loads((tmp_path / f"{stack.artifact_id}.assets.json").read_text())
    images = list(manifest["dockerImages"].values())
    assert len(images) == 1
    source = images[0]["source"]
    assert source["dockerBuildTarget"] == "lambda"
    assert source["platform"] == "linux/arm64"
    assert source["dockerBuildArgs"] == {"GIT_SHA": "abc123"}


def test_no_secret_value_is_in_the_template(rds, bare):
    for template in (rds, bare):
        environment = function_properties(template)["Environment"]["Variables"]
        rendered = json.dumps(environment)

        assert "KC_API_KEY" not in environment  # only the ARN of the secret is given
        assert "KC_API_KEY_SECRET_ARN" in environment
        assert "KC_DATABASE_URL" not in environment
        # (CloudFormation's own reference for the RDS master password is fine: it is
        # resolved by the service at deploy time and never reaches the function.)
        assert "resolve:secretsmanager" not in rendered
        assert "password" not in rendered.lower()


# --- the network and the database -----------------------------------------------------


def test_database_is_private_encrypted_and_not_publicly_accessible(rds):
    rds.has_resource_properties(
        "AWS::RDS::DBInstance",
        {
            "Engine": "postgres",
            "PubliclyAccessible": False,
            "StorageEncrypted": True,
            "DBInstanceClass": "db.t4g.micro",
        },
    )


def test_there_is_no_internet_route_at_all(rds):
    rds.resource_count_is("AWS::EC2::InternetGateway", 0)
    rds.resource_count_is("AWS::EC2::NatGateway", 0)
    rds.resource_count_is("AWS::EC2::Route", 0)  # isolated subnets have no routes


def test_no_security_group_rule_is_open_to_the_world(rds, bare):
    for template in (rds, bare):
        assert "0.0.0.0/0" not in json.dumps(template.to_json())


def test_only_the_function_may_reach_postgres_and_the_endpoint(rds):
    rules = rds.find_resources("AWS::EC2::SecurityGroupIngress")

    assert len(rules) == 2  # Postgres and the Secrets Manager endpoint, nothing else
    for rule in rules.values():
        properties = rule["Properties"]
        assert "SourceSecurityGroupId" in properties  # a security group...
        assert "CidrIp" not in properties  # ...never an address range
    inline = [
        group["Properties"].get("SecurityGroupIngress")
        for group in rds.find_resources("AWS::EC2::SecurityGroup").values()
    ]
    assert not any(inline)  # no ingress hidden inside a group definition


def test_function_sits_in_the_vpc_and_secrets_use_a_private_endpoint(rds):
    assert "VpcConfig" in function_properties(rds)
    rds.has_resource_properties(
        "AWS::EC2::VPCEndpoint",
        {"VpcEndpointType": "Interface", "PrivateDnsEnabled": True},
    )


# --- permissions -------------------------------------------------------------------


def secret_statements(template: Template) -> list[dict]:
    statements = []
    for policy in template.find_resources("AWS::IAM::Policy").values():
        statements += policy["Properties"]["PolicyDocument"]["Statement"]
    return statements


def test_the_function_may_only_read_its_own_secrets(rds):
    for statement in secret_statements(rds):
        actions = statement["Action"]
        actions = [actions] if isinstance(actions, str) else actions
        assert set(actions) <= {
            "secretsmanager:GetSecretValue",
            "secretsmanager:DescribeSecret",
        }, actions
        assert statement["Resource"] != "*"


def test_the_function_never_gets_a_wildcard_resource_in_its_own_policy(bare):
    assert all(s["Resource"] != "*" for s in secret_statements(bare))


# --- the public door ------------------------------------------------------------------


def test_the_api_is_throttled(rds):
    rds.has_resource_properties(
        "AWS::ApiGatewayV2::Stage",
        {
            "StageName": "$default",
            "DefaultRouteSettings": {
                "ThrottlingRateLimit": 10,
                "ThrottlingBurstLimit": 20,
            },
            "AccessLogSettings": Match.object_like({"Format": Match.any_value()}),
        },
    )


def test_every_log_group_has_a_retention_period(rds):
    groups = rds.find_resources("AWS::Logs::LogGroup")

    assert groups
    assert all(g["Properties"].get("RetentionInDays") for g in groups.values())


def test_alarms_exist_for_function_errors_and_api_5xx(rds):
    rds.resource_count_is("AWS::CloudWatch::Alarm", 2)


def test_the_link_and_key_location_are_outputs(rds):
    outputs = rds.to_json()["Outputs"]

    assert {"ApiUrl", "ApiKeySecretArn", "GetApiKeyCommand"} <= set(outputs)


# --- the two modes and the options --------------------------------------------------


def test_database_none_has_no_vpc_no_database_and_no_endpoint(bare):
    bare.resource_count_is("AWS::RDS::DBInstance", 0)
    bare.resource_count_is("AWS::EC2::VPC", 0)
    bare.resource_count_is("AWS::EC2::VPCEndpoint", 0)
    assert "VpcConfig" not in function_properties(bare)
    assert (
        "KC_DATABASE_HOST" not in function_properties(bare)["Environment"]["Variables"]
    )


def test_a_budget_and_alert_topic_exist_only_when_an_email_is_given(rds):
    rds.resource_count_is("AWS::Budgets::Budget", 0)
    rds.resource_count_is("AWS::SNS::Topic", 0)

    with_email = build(alert_email="me@example.com", budget_usd=25)

    with_email.resource_count_is("AWS::Budgets::Budget", 1)
    with_email.resource_count_is("AWS::SNS::Subscription", 1)
    with_email.has_resource_properties(
        "AWS::Budgets::Budget",
        {"Budget": Match.object_like({"BudgetLimit": {"Amount": 25, "Unit": "USD"}})},
    )


def test_provisioned_concurrency_is_off_by_default_and_opt_in(rds):
    rds.resource_count_is("AWS::Lambda::Alias", 0)

    warm = build(database="none", provisioned_concurrency=2)

    warm.has_resource_properties(
        "AWS::Lambda::Alias",
        {"ProvisionedConcurrencyConfig": {"ProvisionedConcurrentExecutions": 2}},
    )


def test_invalid_options_are_rejected_before_anything_is_built():
    with pytest.raises(ValueError, match="database"):
        Config(database="dynamodb")
    with pytest.raises(ValueError, match="throttle_burst"):
        Config(throttle_rate=50, throttle_burst=10)


def test_the_postgres_version_can_be_chosen_at_deploy_time(rds):
    rds.has_resource_properties("AWS::RDS::DBInstance", {"EngineVersion": "17"})

    pinned = build(postgres_version="17.6")

    pinned.has_resource_properties("AWS::RDS::DBInstance", {"EngineVersion": "17.6"})
