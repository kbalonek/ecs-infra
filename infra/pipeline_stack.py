from pathlib import Path

from constructs import Construct
from aws_cdk import (
    Stack,
    pipelines as pipelines,
    aws_ssm as ssm,
)
from .deployment_stage import PipelineStage
from .models import PolyramaApp, MonorepoApp


APPS = [
    PolyramaApp(
        name="demo",
        subdomain_name="demo",
        monorepo_app=MonorepoApp(
            path=Path(__file__).parent.parent / "app",
            django_debug=True,
            app_task_memory_mib=256,
            app_task_desired_count=1,
            app_task_min_scaling_capacity=1,
            app_task_max_scaling_capacity=2,
            worker_task_min_scaling_capacity=1,
            worker_task_max_scaling_capacity=2,
            worker_scaling_steps=[
                {"upper": 0, "change": 0},  # 0 msgs = 1 workers
                {"lower": 10, "change": +1},  # 10 msgs = 2 workers
            ],
        ),
    ),
    PolyramaApp(
        name="test",
        subdomain_name="test",
        monorepo_app=MonorepoApp(
            path=Path(__file__).parent.parent / "app",
            django_debug=True,
            app_task_memory_mib=256,
            app_task_desired_count=1,
            app_task_min_scaling_capacity=1,
            app_task_max_scaling_capacity=2,
            worker_task_min_scaling_capacity=1,
            worker_task_max_scaling_capacity=2,
            worker_scaling_steps=[
                {"upper": 0, "change": 0},  # 0 msgs = 1 workers
                {"lower": 10, "change": +1},  # 10 msgs = 2 workers
            ],
        ),
    ),
]


class PlatformPipelineStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        repository: str,
        branch: str,
        ssm_gh_connection_param: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.repository = repository
        self.branch = branch
        self.ssm_gh_connection_param = ssm_gh_connection_param
        self.gh_connection_arn = ssm.StringParameter.value_for_string_parameter(
            self, ssm_gh_connection_param
        )
        aws_env = kwargs.get("env")
        pipeline = pipelines.CodePipeline(
            self,
            "Pipeline",
            synth=pipelines.ShellStep(
                "Synth",
                input=pipelines.CodePipelineSource.connection(
                    self.repository,
                    self.branch,
                    connection_arn=self.gh_connection_arn,
                    trigger_on_push=True,
                ),
                commands=[
                    "npm install -g aws-cdk",  # Installs the cdk cli on Codebuild
                    "pip install poetry",  # Instructs Codebuild to install required packages
                    "poetry install",
                    "npx cdk synth PlatformPipeline",
                ],
            ),
        )

        # Deploy to production environment
        self.production_env = PipelineStage(
            self,
            "Prod",
            env=aws_env,  # AWS Account and Region
            apps_config=APPS,
            domain_name="polyrama.co.uk",
        )
        pipeline.add_stage(self.production_env)
        # Deploy to production after manual approval
        # self.production_env = PlatformPipelineStage(
        #     self, "PolyramaProd",
        #     env=aws_env,  # AWS Account and Region
        #     django_debug=False,
        #     domain_name="scalabledjango.com",
        #     db_auto_pause_minutes=0,  # Keep the database always up in production
        #     app_task_min_scaling_capacity=2,
        #     app_task_max_scaling_capacity=5,
        #     worker_task_min_scaling_capacity=2,
        #     worker_task_max_scaling_capacity=4,
        #     worker_scaling_steps=[
        #         {"upper": 0, "change": 0},     # 0 msgs = 1 workers
        #         {"lower": 100, "change": +1},  # > 100 msg = 2 worker
        #         {"lower": 200, "change": +1},  # > 200 msgs = 3 workers
        #         {"lower": 500, "change": +2},  # > 500 msgs = 5 workers
        #     ]
        # )
        # pipeline.add_stage(
        #     self.production_env,
        #     pre=[
        #         pipelines.ManualApprovalStep("PromoteToProduction")
        #     ]
        # )
