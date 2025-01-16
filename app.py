#!/usr/bin/env python3
import os
import aws_cdk as cdk
from aws_cdk import (
    Environment,
)
from infra.pipeline_stack import PlatformPipelineStack


app = cdk.App()
pipeline = PlatformPipelineStack(
    app,
    "Polyrama",
    repository="kbalonek/ecs-infra",
    branch="main",
    ssm_gh_connection_param="/Github/Connection",
    env=Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'),
        region=os.getenv('CDK_DEFAULT_REGION')
    ),
)
app.synth()
