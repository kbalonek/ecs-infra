import os
from constructs import Construct
from aws_cdk import (
    CfnOutput,
    Fn,
    Stage,
    aws_certificatemanager as acm,
    aws_ecs as ecs,
    aws_secretsmanager as secretsmanager,
    aws_elasticloadbalancingv2 as elbv2,
)
from infra.domain_stack import DomainStack
from infra.network_stack import NetworkStack
from infra.database_stack import DatabaseStack
from infra.models import PolyramaApp
from infra.service_stack import ServiceStack
from infra.static_files_stack import StaticFilesStack
from infra.queues_stack import QueuesStack
from infra.backend_workers_stack import BackendWorkersStack
from infra.external_secrets_stack import ExternalSecretsStack
from infra.dns_route_to_alb_stack import DnsRouteToAlbStack
from infra.load_balancer_stack import LoadBalancerStack


class PipelineStage(Stage):

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        domain_name: str,
        apps_config: list[PolyramaApp],
        **kwargs,
    ):

        super().__init__(scope, construct_id, **kwargs)
        self.domain_name = domain_name
        aws_env = kwargs.get("env")
        self.network = NetworkStack(
            self,
            "Network",
            env=aws_env,  # AWS Account and Region
        )

        self.database = DatabaseStack(
            self,
            "Database",
            env=aws_env,  # AWS Account and Region
            vpc=self.network.vpc,
            apps_config=apps_config,
        )

        self.domain = DomainStack(
            self,
            "Domain",
            env=aws_env,
            domain_name=self.domain_name,
            subdomains=[app.subdomain_name for app in apps_config],
        )

        # Create LoadBalancerStack after domain but before service
        self.load_balancer = LoadBalancerStack(
            self,
            "LoadBalancer",
            env=aws_env,
            vpc=self.network.vpc,
            security_group=self.network.alb_security_group,
            domain_certificate=self.domain.certificate,
            auto_scaling_group=self.network.auto_scaling_group,
        )


        for app in filter(lambda app: bool(app.monorepo_app), apps_config):
            # Serve static files for the Backoffice (django-admin)
            static_files = StaticFilesStack(
                self,
                f"{app.name}StaticFiles",
                env=aws_env,  # AWS Account and Region
                app_name=app.name,
                cors_allowed_origins=[
                    (
                        f"https://{app.subdomain_name}.{self.domain_name}"
                        if app.subdomain_name
                        else f"https://{self.domain_name}"
                    )
                ],
            )
            queues = QueuesStack(
                self,
                f"{app.name}Queues",
                env=aws_env,  # AWS Account and Region
                app_name=app.name,
            )

            app_env_vars = {
                "DJANGO_SETTINGS_MODULE": "app.settings.prod",
                "DJANGO_DEBUG": str(app.monorepo_app.django_debug),
                "AWS_ACCOUNT_ID": os.getenv("CDK_DEFAULT_ACCOUNT"),
                "AWS_STATIC_FILES_BUCKET_NAME": static_files.s3_bucket.bucket_name,
                "AWS_STATIC_FILES_CLOUDFRONT_URL": static_files.cloudfront_distro.distribution_domain_name,
                "SQS_DEFAULT_QUEUE_URL": queues.default_queue.queue_url,
                "CELERY_TASK_ALWAYS_EAGER": "False",
            }

            secrets = ExternalSecretsStack(
                self,
                f"{app.name}ExternalParameters",
                env=aws_env,  # AWS Account and Region
                app_name=app.name
            )

            django_app = ServiceStack(
                self,
                f"{app.name}Service",
                env=aws_env,  # AWS Account and Region
                app_name=app.name,
                queue=queues.default_queue,
                env_vars=app_env_vars,
                secrets=secrets.app_secrets,
                app_path=app.monorepo_app.path,
                task_memory_mib=app.monorepo_app.app_task_memory_mib,
                task_desired_count=app.monorepo_app.app_task_desired_count,
                task_min_scaling_capacity=app.monorepo_app.app_task_min_scaling_capacity,
                task_max_scaling_capacity=app.monorepo_app.app_task_max_scaling_capacity,
            )
            # Grant permissions to the app to put messages in hte queue
            queues.default_queue.grant_send_messages(
                django_app.task_definition.task_role
            )
            static_files.s3_bucket.grant_write(django_app.task_definition.task_role)

            # self.workers = BackendWorkersStack(
            #     self,
            #     "Workers",
            #     env=aws_env,  # AWS Account and Region
            #     vpc=self.network.vpc,
            #     ecs_cluster=self.network.ecs_cluster,
            #     queue=self.queues.default_queue,
            #     env_vars=self.app_env_vars,
            #     secrets=self.secrets.app_secrets,
            #     task_cpu=256,
            #     task_memory_mib=512,
            #     task_min_scaling_capacity=self.worker_task_min_scaling_capacity,
            #     task_max_scaling_capacity=self.worker_task_max_scaling_capacity,
            #     scaling_steps=self.worker_scaling_steps
            # )

            # Route requests made in the domain to the ALB
            dns = DnsRouteToAlbStack(
                self,
                f"{app.name}DnsToAlb",
                env=aws_env,  # AWS Account and Region
                hosted_zone=self.domain.hosted_zone,
                subdomain=app.subdomain_name,
                alb=self.load_balancer.load_balancer,  # Use the new ALB
            )
