from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
    aws_ec2 as ec2,
    aws_sqs as sqs,
    aws_ecs as ecs,
    aws_certificatemanager as acm,
    aws_elasticloadbalancingv2 as elbv2,
    aws_ssm as ssm,
    aws_logs as logs
)
from constructs import Construct


class ServiceStack(Stack):

    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            ecs_cluster: ecs.Cluster,
            domain_certificate: acm.Certificate,
            queue: sqs.Queue,
            env_vars: dict,
            secrets: dict,
            alb_listener: elbv2.ApplicationListener,
            task_cpu: int = 256,
            task_memory_mib: int = 1024,
            task_desired_count: int = 2,
            task_min_scaling_capacity: int = 2,
            task_max_scaling_capacity: int = 4,
            **kwargs
    ) -> None:

        super().__init__(scope, construct_id, **kwargs)
        self.ecs_cluster = ecs_cluster
        self.domain_certificate = domain_certificate
        self.queue = queue
        self.env_vars = env_vars
        self.secrets = secrets
        self.task_cpu = task_cpu
        self.task_memory_mib = task_memory_mib
        self.task_desired_count = task_desired_count
        self.task_min_scaling_capacity = task_min_scaling_capacity
        self.task_max_scaling_capacity = task_max_scaling_capacity

        # Prepare parameters
        self.container_name = f"django_app"
        
        # Create Task Definition
        self.task_definition = ecs.Ec2TaskDefinition(
            self, "TaskDef")

        container = self.task_definition.add_container(
            "web",
            image=ecs.ContainerImage.from_asset(
                directory="app/",
                file="docker/app/Dockerfile",
                target="prod"
            ),
            container_name=self.container_name,
            memory_limit_mib=self.task_memory_mib,
            environment=self.env_vars,
            secrets=self.secrets,
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="django-app",
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
            cluster=self.ecs_cluster,
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

        

        # Save useful values in in SSM
        self.ecs_cluster_name_param = ssm.StringParameter(
            self,
            "EcsClusterNameParam",
            parameter_name=f"/{scope.stage_name}/EcsClusterNameParam",
            string_value=self.ecs_cluster.cluster_name
        )
        self.task_def_arn_param = ssm.StringParameter(
            self,
            "TaskDefArnParam",
            parameter_name=f"/{scope.stage_name}/TaskDefArnParam",
            string_value=self.task_definition.task_definition_arn
        )
        self.task_def_family_param = ssm.StringParameter(
            self,
            "TaskDefFamilyParam",
            parameter_name=f"/{scope.stage_name}/TaskDefFamilyParam",
            string_value=f"family:{self.task_definition.family}"
        )
        self.exec_role_arn_param = ssm.StringParameter(
            self,
            "TaskExecRoleArnParam",
            parameter_name=f"/{scope.stage_name}/TaskExecRoleArnParam",
            string_value=self.task_definition.execution_role.role_arn
        )
        self.task_role_arn_param = ssm.StringParameter(
            self,
            "TaskRoleArnParam",
            parameter_name=f"/{scope.stage_name}/TaskRoleArnParam",
            string_value=self.task_definition.task_role.role_arn
        )
