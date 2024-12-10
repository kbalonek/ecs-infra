from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
    aws_autoscaling as autoscaling,
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
            vpc: ec2.Vpc,
            ecs_cluster: ecs.Cluster,
            auto_scaling_group: autoscaling.AutoScalingGroup,
            domain_certificate: acm.Certificate,
            queue: sqs.Queue,
            env_vars: dict,
            secrets: dict,
            alb_security_group: ec2.SecurityGroup,
            task_cpu: int = 256,
            task_memory_mib: int = 1024,
            task_desired_count: int = 2,
            task_min_scaling_capacity: int = 2,
            task_max_scaling_capacity: int = 4,
            **kwargs
    ) -> None:

        super().__init__(scope, construct_id, **kwargs)
        self.vpc = vpc
        self.ecs_cluster = ecs_cluster
        self.auto_scaling_group = auto_scaling_group
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

        # # Create the load balancer, ECS service and the task for the Django App
        # self.alb_service = ecs_patterns.ApplicationLoadBalancedEc2Service(
        #     self,
        #     f"App",
        #     protocol=elbv2.ApplicationProtocol.HTTPS,
        #     certificate=self.domain_certificate,
        #     redirect_http=True,
        #     cluster=self.ecs_cluster, 
        #     memory_limit_mib=self.task_memory_mib,  # Default is 512
        #     desired_count=self.task_desired_count,  # Default is 1
        #     task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
        #         image=ecs.ContainerImage.from_asset(
        #             directory="app/",
        #             file="docker/app/Dockerfile",
        #             target="prod"
        #         ),
        #         # image=ecs.ContainerImage.from_registry("amazon/amazon-ecs-sample"),
        #         container_name=self.container_name,
        #         container_port=8000,
        #         environment=self.env_vars,
        #         secrets=self.secrets
        #     ),
        #     public_load_balancer=True
        # )
        
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

        # Create ALB
        self.load_balancer = elbv2.ApplicationLoadBalancer(
            self, "LB",
            vpc=vpc,
            internet_facing=True,
            security_group=alb_security_group
        )
        self.load_balancer.add_redirect()

        listener = self.load_balancer.add_listener(
            "PublicListener",
            protocol=elbv2.ApplicationProtocol.HTTPS,
            open=True,
            certificates=[domain_certificate],
        )

        auto_scaling_group.connections.allow_from(
            self.load_balancer, 
            port_range=ec2.Port.tcp_range(32768, 65535), 
            description="allow incoming traffic from ALB",
        )

        health_check = elbv2.HealthCheck(
            interval=Duration.seconds(30),
            path="/status/",
            timeout=Duration.seconds(5),
            healthy_threshold_count=3,
            unhealthy_threshold_count=2
        )

        # Attach ALB to ECS Service
        listener.add_targets(
            "ECS",
            port=8000,
            targets=[self.service],
            health_check=health_check,
        )

        CfnOutput(
            self, "LoadBalancerDNS",
            value="http://"+self.load_balancer.load_balancer_dns_name
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
