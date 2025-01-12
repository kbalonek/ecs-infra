from pathlib import Path

from aws_cdk import (
    Duration,
    Fn,
    Stack,
    aws_ecs as ecs,
    aws_certificatemanager as acm,
    aws_elasticloadbalancingv2 as elbv2,
    aws_ec2 as ec2,
    aws_ssm as ssm,
    aws_logs as logs,
    aws_sqs as sqs,
)
from constructs import Construct
from infra.models import PolyramaApp

class ServiceStack(Stack):

    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            queue: sqs.Queue,
            env_vars: dict,
            secrets: dict,
            app_name: str,
            app_path: Path,
            task_memory_mib: int = 1024,
            task_desired_count: int = 2,
            task_min_scaling_capacity: int = 2,
            task_max_scaling_capacity: int = 4,
            **kwargs
    ) -> None:

        super().__init__(scope, construct_id, **kwargs)
        self.queue = queue
        self.env_vars = env_vars
        self.secrets = secrets
        self.task_memory_mib = task_memory_mib
        self.task_desired_count = task_desired_count
        self.task_min_scaling_capacity = task_min_scaling_capacity
        self.task_max_scaling_capacity = task_max_scaling_capacity

        # Prepare parameters
        self.container_name = f"django_app"
        alb_listener = elbv2.ApplicationListener.from_application_listener_attributes(
            self,
            f"AlbListener",
            listener_arn=Fn.import_value(f"alb-listener-arn"),
            security_group=ec2.SecurityGroup.from_security_group_id(
                self,
                f"AlbSecurityGroup",
                Fn.import_value(f"alb-security-group-id")
            )
        )
        certificate = acm.Certificate.from_certificate_arn(
            self,
            f"Certificate",
            certificate_arn=Fn.import_value(f"certificate-arn"),
        )

        ecs_cluster = ecs.Cluster.from_cluster_attributes(
            self,
            f"EcsCluster",
            cluster_name=Fn.import_value(f"ecs-cluster-name"),
            vpc=ec2.Vpc.from_lookup(
                self,
                f"Vpc",
                vpc_id=Fn.import_value(f"vpc-id")
            )
        )

        # Create Task Definition
        self.task_definition = ecs.Ec2TaskDefinition(
            self, "TaskDef")

        container = self.task_definition.add_container(
            "web",
            image=ecs.ContainerImage.from_asset(
                directory=str(app_path),
                file="docker/app/Dockerfile",
                target="prod"
            ),
            container_name=self.container_name,
            memory_limit_mib=self.task_memory_mib,
            environment=self.env_vars,
            secrets=self.secrets,
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix=f"{app_name}-app",
                log_retention=logs.RetentionDays.ONE_MONTH
            ),
        )

        port_mapping = ecs.PortMapping(
            container_port=8000,
            host_port=0,
            protocol=ecs.Protocol.TCP
        )

        container.add_port_mappings(port_mapping)

        # Create Service
        self.service = ecs.Ec2Service(
            self, "Service",
            cluster=ecs_cluster,
            task_definition=self.task_definition,
            desired_count=self.task_desired_count,
        )

        # Autoscaling based on CPU utilization
        scalable_target = self.service.auto_scale_task_count(
            min_capacity=self.task_min_scaling_capacity,
            max_capacity=self.task_max_scaling_capacity
        )
        scalable_target.scale_on_cpu_utilization(
            f"CpuScaling",
            target_utilization_percent=75,
        ) 

        health_check = elbv2.HealthCheck(
            interval=Duration.seconds(30),
            path="/status/",
            timeout=Duration.seconds(5),
            healthy_threshold_count=3,
            unhealthy_threshold_count=2
        )

        # Attach ALB to ECS Service
        alb_listener.add_targets(
            "ECS",
            port=8000,
            targets=[self.service],
            health_check=health_check,
        )

        self.task_def_arn_param = ssm.StringParameter(
            self,
            "TaskDefArnParam",
            parameter_name=f"{app_name}-task-def-arn",
            string_value=self.task_definition.task_definition_arn
        )
        self.task_def_family_param = ssm.StringParameter(
            self,
            "TaskDefFamilyParam",
            parameter_name=f"{app_name}-task-def-family",
            string_value=f"family:{self.task_definition.family}"
        )
        self.exec_role_arn_param = ssm.StringParameter(
            self,
            "TaskExecRoleArnParam",
            parameter_name=f"{app_name}-task-exec-role-arn",
            string_value=self.task_definition.execution_role.role_arn
        )
        self.task_role_arn_param = ssm.StringParameter(
            self,
            "TaskRoleArnParam",
            parameter_name=f"{app_name}-task-role-arn",
            string_value=self.task_definition.task_role.role_arn
        )
