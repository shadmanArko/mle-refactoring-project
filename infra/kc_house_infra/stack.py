"""One stack: a Lambda container behind an HTTP API, with an optional private Postgres.

    database="rds"   Lambda in an isolated VPC, RDS Postgres, Secrets Manager endpoint.
    database="none"  Lambda only. Estimates and pages work; /api/houses returns 503.

No secret is ever placed in the template or in an environment variable: the function is
given secret ARNs and reads the values itself (see src/kc_house/api/secrets.py).
"""

import os

os.environ.setdefault("JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION", "1")

from dataclasses import dataclass
from pathlib import Path

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import (
    aws_apigatewayv2 as apigwv2,
)
from aws_cdk import (
    aws_apigatewayv2_integrations as integrations,
)
from aws_cdk import (
    aws_budgets as budgets,
)
from aws_cdk import (
    aws_cloudwatch as cloudwatch,
)
from aws_cdk import (
    aws_cloudwatch_actions as cw_actions,
)
from aws_cdk import (
    aws_ec2 as ec2,
)
from aws_cdk import (
    aws_ecr_assets as ecr_assets,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from aws_cdk import (
    aws_logs as logs,
)
from aws_cdk import (
    aws_rds as rds,
)
from aws_cdk import (
    aws_secretsmanager as secretsmanager,
)
from aws_cdk import (
    aws_sns as sns,
)
from aws_cdk import (
    aws_sns_subscriptions as subscriptions,
)
from constructs import Construct

REPO_ROOT = Path(__file__).resolve().parents[2]
DATABASES = ("rds", "none")


@dataclass(frozen=True)
class Config:
    database: str = "rds"
    # "17" lets RDS pick its default minor version. If AWS rejects it, pass a
    # supported one: -c postgres_version=17.6 (aws rds describe-db-engine-versions).
    postgres_version: str = "17"
    memory_mb: int = 2048
    timeout_seconds: int = 30
    throttle_rate: int = 10  # sustained requests per second, whole API
    throttle_burst: int = 20
    provisioned_concurrency: int = 0  # warm instances; costs money while idle
    git_sha: str = "unknown"
    github_url: str = "https://github.com/shadmanArko/mle-refactoring-project"
    alert_email: str | None = None  # alarms and the budget notify this address
    budget_usd: int = 30  # monthly, only created when alert_email is set

    def __post_init__(self) -> None:
        if self.database not in DATABASES:
            raise ValueError(
                f"database must be one of {DATABASES}, got {self.database!r}"
            )
        if self.throttle_burst < self.throttle_rate:
            raise ValueError("throttle_burst must be at least throttle_rate")


class KcHouseStack(Stack):
    def __init__(
        self, scope: Construct, construct_id: str, *, config: Config, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.config = config

        api_key = secretsmanager.Secret(
            self,
            "ApiKey",
            description="X-API-Key that allows writes to /api/houses",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                password_length=32, exclude_punctuation=True
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )
        environment = {
            "KC_MODEL_DIR": "/app/artifacts",
            "KC_API_KEY_SECRET_ARN": api_key.secret_arn,
            "KC_GITHUB_URL": config.github_url,
            "KC_LOG_LEVEL": "INFO",
        }

        network: dict = {}
        self.database: rds.DatabaseInstance | None = None
        if config.database == "rds":
            network, environment = self._private_database(environment)

        self.function = self._function(environment, network)
        api_key.grant_read(self.function)
        if self.database is not None and self.database.secret is not None:
            self.database.secret.grant_read(self.function)
            self.database.connections.allow_default_port_from(self.function)

        stage = self._http_api(self.function)
        self._alarms(self.function, stage)

        CfnOutput(self, "ApiUrl", value=stage.url or "", description="Public link")
        CfnOutput(self, "ApiKeySecretArn", value=api_key.secret_arn)
        CfnOutput(
            self,
            "GetApiKeyCommand",
            value=(
                f"aws secretsmanager get-secret-value --secret-id {api_key.secret_arn} "
                "--query SecretString --output text"
            ),
        )

    def _private_database(self, environment: dict) -> tuple[dict, dict]:
        """Isolated VPC (no internet, no NAT) with Postgres inside it."""
        vpc = ec2.Vpc(
            self,
            "Vpc",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="private",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                )
            ],
        )
        function_sg = ec2.SecurityGroup(
            self,
            "FunctionSg",
            vpc=vpc,
            description="Lambda function: may reach only Postgres and Secrets Manager",
            allow_all_outbound=False,
        )
        endpoint_sg = ec2.SecurityGroup(
            self,
            "EndpointSg",
            vpc=vpc,
            description="Secrets Manager endpoint: HTTPS from the function only",
            allow_all_outbound=False,
        )
        database_sg = ec2.SecurityGroup(
            self,
            "DatabaseSg",
            vpc=vpc,
            description="Postgres: accepts connections from the function only",
            allow_all_outbound=False,
        )
        # Without a NAT gateway the function reaches Secrets Manager through an
        # interface endpoint (one AZ is enough for a demo). open=False stops CDK from
        # also admitting the whole VPC range.
        endpoint = vpc.add_interface_endpoint(
            "SecretsManagerEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
            subnets=ec2.SubnetSelection(subnets=[vpc.isolated_subnets[0]]),
            security_groups=[endpoint_sg],
            open=False,
        )
        endpoint.connections.allow_from(function_sg, ec2.Port.tcp(443))

        self.database = rds.DatabaseInstance(
            self,
            "Database",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.of(
                    self.config.postgres_version,
                    self.config.postgres_version.split(".")[0],
                )
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE4_GRAVITON, ec2.InstanceSize.MICRO
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[database_sg],
            database_name="houses",
            credentials=rds.Credentials.from_generated_secret("kc"),
            allocated_storage=20,
            storage_encrypted=True,
            publicly_accessible=False,
            backup_retention=Duration.days(1),
            # A demo must be easy to tear down. Turn these around for real data.
            deletion_protection=False,
            removal_policy=RemovalPolicy.DESTROY,
            delete_automated_backups=True,
        )
        environment = environment | {
            "KC_DATABASE_SECRET_ARN": self.database.secret.secret_arn,  # type: ignore[union-attr]
            "KC_DATABASE_HOST": self.database.db_instance_endpoint_address,
            "KC_DATABASE_PORT": self.database.db_instance_endpoint_port,
            "KC_DATABASE_NAME": "houses",
        }
        network = {
            "vpc": vpc,
            "vpc_subnets": ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            "security_groups": [function_sg],
        }
        return network, environment

    def _function(
        self, environment: dict, network: dict
    ) -> lambda_.DockerImageFunction:
        config = self.config
        return lambda_.DockerImageFunction(
            self,
            "Api",
            description="King County house price estimator (FastAPI on Lambda)",
            code=lambda_.DockerImageCode.from_image_asset(
                str(REPO_ROOT),
                target="lambda",
                platform=ecr_assets.Platform.LINUX_ARM64,
                build_args={"GIT_SHA": config.git_sha},
            ),
            architecture=lambda_.Architecture.ARM_64,
            memory_size=config.memory_mb,
            timeout=Duration.seconds(config.timeout_seconds),
            environment=environment,
            log_group=logs.LogGroup(
                self,
                "ApiLogs",
                retention=logs.RetentionDays.ONE_MONTH,
                removal_policy=RemovalPolicy.DESTROY,
            ),
            **network,
        )

    def _http_api(self, function: lambda_.DockerImageFunction) -> apigwv2.HttpStage:
        config = self.config
        handler: lambda_.IFunction = function
        if config.provisioned_concurrency > 0:
            handler = function.add_alias(
                "live",
                provisioned_concurrent_executions=config.provisioned_concurrency,
            )
        api = apigwv2.HttpApi(
            self,
            "HttpApi",
            api_name="kc-house",
            description="Public front door for the King County estimator",
            create_default_stage=False,
            default_integration=integrations.HttpLambdaIntegration("Lambda", handler),
        )
        stage = apigwv2.HttpStage(
            self,
            "DefaultStage",
            http_api=api,
            stage_name="$default",
            auto_deploy=True,
            throttle=apigwv2.ThrottleSettings(
                rate_limit=config.throttle_rate, burst_limit=config.throttle_burst
            ),
        )
        access_logs = logs.LogGroup(
            self,
            "AccessLogs",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )
        stage.node.default_child.access_log_settings = (  # type: ignore[union-attr]
            apigwv2.CfnStage.AccessLogSettingsProperty(
                destination_arn=access_logs.log_group_arn,
                format=(
                    '{"requestId":"$context.requestId","ip":"$context.identity.sourceIp",'
                    '"method":"$context.httpMethod","path":"$context.path",'
                    '"status":"$context.status","latencyMs":"$context.responseLatency",'
                    '"integrationError":"$context.integrationErrorMessage"}'
                ),
            )
        )
        return stage

    def _alarms(
        self, function: lambda_.DockerImageFunction, stage: apigwv2.HttpStage
    ) -> None:
        config = self.config
        topic = None
        if config.alert_email:
            topic = sns.Topic(self, "Alerts")
            topic.add_subscription(subscriptions.EmailSubscription(config.alert_email))
            budgets.CfnBudget(
                self,
                "MonthlyBudget",
                budget=budgets.CfnBudget.BudgetDataProperty(
                    budget_type="COST",
                    time_unit="MONTHLY",
                    budget_limit=budgets.CfnBudget.SpendProperty(
                        amount=config.budget_usd, unit="USD"
                    ),
                ),
                notifications_with_subscribers=[
                    budgets.CfnBudget.NotificationWithSubscribersProperty(
                        notification=budgets.CfnBudget.NotificationProperty(
                            notification_type=notification,
                            comparison_operator="GREATER_THAN",
                            threshold=threshold,
                            threshold_type="PERCENTAGE",
                        ),
                        subscribers=[
                            budgets.CfnBudget.SubscriberProperty(
                                subscription_type="EMAIL", address=config.alert_email
                            )
                        ],
                    )
                    for notification, threshold in (("ACTUAL", 80), ("FORECASTED", 100))
                ],
            )

        five_minutes = Duration.minutes(5)
        alarms = {
            "FunctionErrors": function.metric_errors(
                period=five_minutes, statistic="Sum"
            ),
            "Api5xx": cloudwatch.Metric(
                namespace="AWS/ApiGateway",
                metric_name="5xx",
                dimensions_map={"ApiId": stage.api.api_id},
                period=five_minutes,
                statistic="Sum",
            ),
        }
        for name, metric in alarms.items():
            alarm = cloudwatch.Alarm(
                self,
                name,
                metric=metric,
                threshold=1,
                evaluation_periods=1,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            )
            if topic is not None:
                alarm.add_alarm_action(cw_actions.SnsAction(topic))
