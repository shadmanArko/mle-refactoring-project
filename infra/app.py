"""CDK entry point.  Choose options with ``-c name=value``, for example:

npx aws-cdk@2 deploy -c database=none -c alert_email=me@example.com
"""

import os

os.environ.setdefault("JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION", "1")

import aws_cdk as cdk
from kc_house_infra.stack import Config, KcHouseStack

app = cdk.App()


def option(name: str, default):
    """Read ``-c name=value``; text values are converted to the default's type."""
    value = app.node.try_get_context(name)
    if value is None:
        return default
    return value if default is None else type(default)(value)


defaults = Config()
config = Config(
    database=option("database", defaults.database),
    postgres_version=option("postgres_version", defaults.postgres_version),
    memory_mb=option("memory_mb", defaults.memory_mb),
    timeout_seconds=option("timeout_seconds", defaults.timeout_seconds),
    throttle_rate=option("throttle_rate", defaults.throttle_rate),
    throttle_burst=option("throttle_burst", defaults.throttle_burst),
    provisioned_concurrency=option(
        "provisioned_concurrency", defaults.provisioned_concurrency
    ),
    git_sha=option("git_sha", defaults.git_sha),
    github_url=option("github_url", defaults.github_url),
    alert_email=option("alert_email", None),
    budget_usd=option("budget_usd", defaults.budget_usd),
)

KcHouseStack(
    app,
    "KcHouse",
    config=config,
    description="King County house price estimator on AWS Lambda",
)
cdk.Tags.of(app).add("project", "kc-house")
app.synth()
