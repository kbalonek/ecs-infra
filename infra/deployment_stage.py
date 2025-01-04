import os
from constructs import Construct
from aws_cdk import (
    Stage,
    Environment,
    aws_rds as rds,
    aws_route53 as route53,
)
from infra.domain_stack import DomainStack
from infra.network_stack import NetworkStack
from infra.database_stack import DatabaseStack
from infra.service_stack import ServiceStack
from infra.static_files_stack import StaticFilesStack
from infra.queues_stack import QueuesStack
from infra.backend_workers_stack import BackendWorkersStack
from infra.external_secrets_stack import ExternalSecretsStack
from infra.dns_route_to_alb_stack import DnsRouteToAlbStack
from infra.load_balancer_stack import LoadBalancerStack


class PlatformPipelineStage(Stage):

    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            django_debug: bool,
            # TODO move domain and subdomain into apps_config
            apps_config: list[dict],
           
            **kwargs
    ):

        super().__init__(scope, construct_id, **kwargs)
        self.django_debug = django_debug
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
        
        # Serve static files for the Backoffice (django-admin)
        allowed_origins = [app.domain for app in apps_config]
        self.static_files = StaticFilesStack(
            self,
            "StaticFiles",
            env=aws_env,  # AWS Account and Region
            cors_allowed_origins=[
                f"https://{self.subdomain}.{self.domain_name}" if self.subdomain else f"https://{self.domain_name}"
            ]
        )
        self.queues = QueuesStack(
            self,
            "Queues",
            env=aws_env,  # AWS Account and Region
        )
        
        self.app_env_vars = {
            "DJANGO_SETTINGS_MODULE": "app.settings.prod",
            "DJANGO_DEBUG": str(self.django_debug),
            "AWS_ACCOUNT_ID": os.getenv('CDK_DEFAULT_ACCOUNT'),
            "AWS_STATIC_FILES_BUCKET_NAME":  self.static_files.s3_bucket.bucket_name,
            "AWS_STATIC_FILES_CLOUDFRONT_URL": self.static_files.cloudfront_distro.distribution_domain_name,
            "SQS_DEFAULT_QUEUE_URL": self.queues.default_queue.queue_url,
            "CELERY_TASK_ALWAYS_EAGER": "False"
        }

        self.secrets = ExternalSecretsStack(
            self,
            "ExternalParameters",
            env=aws_env,  # AWS Account and Region
            name_prefix=f"/{self.stage_name}/",
            # TODO reference the app db?
            database_secrets=self.database.rds.secret,
        )
        
        self.domain = DomainStack(
            self,
            "Domain",
            env=aws_env,
            domain_name=self.domain_name,
            subdomain=self.subdomain,
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
        
        self.django_app = ServiceStack(
            self,
            "Service",
            env=aws_env,  # AWS Account and Region
            ecs_cluster=self.network.ecs_cluster,
            alb_listener=self.load_balancer.https_listener,
            domain_certificate=self.domain.certificate,
            queue=self.queues.default_queue,
            env_vars=self.app_env_vars,
            secrets=self.secrets.app_secrets,
            task_cpu=256,
            task_memory_mib=386,
            task_desired_count=self.app_task_min_scaling_capacity,
            task_min_scaling_capacity=self.app_task_min_scaling_capacity,
            task_max_scaling_capacity=self.app_task_max_scaling_capacity,
            
        )
        # Grant permissions to the app to put messages in hte queue
        self.queues.default_queue.grant_send_messages(
            self.django_app.task_definition.task_role
        )
        self.static_files.s3_bucket.grant_write(
            self.django_app.task_definition.task_role
        )
        
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
        self.dns = DnsRouteToAlbStack(
            self,
            "DnsToAlb",
            env=aws_env,  # AWS Account and Region
            hosted_zone=self.domain.hosted_zone,
            subdomain=self.subdomain,
            alb=self.load_balancer.load_balancer,  # Use the new ALB
        )
