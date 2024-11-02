from aws_cdk import (
    Stack,
    aws_autoscaling as autoscaling,
    aws_ec2 as ec2,
    aws_ssm as ssm,
    aws_ecs as ecs,
    aws_iam as iam,
)
from constructs import Construct


class NetworkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Our network in the cloud
        self.vpc = ec2.Vpc(
            self,
            "VPC",
            max_azs=2,  # default is all AZs in region
            nat_gateways=0,  # No Nat GWs are required as we will add VPC endpoints
            enable_dns_hostnames=True,
            enable_dns_support=True,
        )
        self.ecs_cluster = ecs.Cluster(self, f"ECSCluster", vpc=self.vpc)

        # adapted from https://repost.aws/questions/QUngx5J6lSSE6VMFPQVqELSw/cdkv2-ecs-with-ec2-launch-type-stuck-in-aws-ecs-service-create-in-progress
        launch_template = ec2.LaunchTemplate(
            self,
            "ASG-LaunchTemplate",
            instance_type=ec2.InstanceType("t3.micro"),
            machine_image=ecs.EcsOptimizedImage.amazon_linux2(),
            user_data=ec2.UserData.for_linux(),
            role=iam.Role(
                self,
                "InstanceRole",
                assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
                managed_policies=[
                    iam.ManagedPolicy.from_aws_managed_policy_name(
                        "service-role/AmazonEC2ContainerServiceforEC2Role"
                    )
                ],
            ),
        )

        auto_scaling_group = autoscaling.AutoScalingGroup(
            self,
            "ASG",
            vpc=self.vpc,
            max_capacity=1,
            mixed_instances_policy=autoscaling.MixedInstancesPolicy(
                instances_distribution=autoscaling.InstancesDistribution(
                    on_demand_percentage_above_base_capacity=50
                ),
                launch_template=launch_template,
            ),
        )

        capacity_provider = ecs.AsgCapacityProvider(
            self,
            "AsgCapacityProvider",
            auto_scaling_group=auto_scaling_group,
            machine_image_type=ecs.MachineImageType.AMAZON_LINUX_2,
        )

        self.ecs_cluster.add_asg_capacity_provider(capacity_provider)

        # Add VPC endpoints to keep the traffic inside AWS
        self.s3_private_link = ec2.GatewayVpcEndpoint(
            self,
            "S3GWEndpoint",
            vpc=self.vpc,
            service=ec2.GatewayVpcEndpointAwsService.S3,
        )
        self.ecr_api_private_link = ec2.InterfaceVpcEndpoint(
            self,
            "ECRapiEndpoint",
            vpc=self.vpc,
            service=ec2.InterfaceVpcEndpointAwsService.ECR,
            open=True,
            private_dns_enabled=True,
        )
        self.ecr_dkr_private_link = ec2.InterfaceVpcEndpoint(
            self,
            "ECRdkrEndpoint",
            vpc=self.vpc,
            service=ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
            open=True,
            private_dns_enabled=True,
        )
        self.cloudwatch_private_link = ec2.InterfaceVpcEndpoint(
            self,
            "CloudWatchEndpoint",
            vpc=self.vpc,
            service=ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
            open=True,
            private_dns_enabled=True,
        )
        self.secrets_manager_private_link = ec2.InterfaceVpcEndpoint(
            self,
            "SecretsManagerEndpoint",
            vpc=self.vpc,
            service=ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
            open=True,
            private_dns_enabled=True,
        )
        self.sqs_private_link = ec2.InterfaceVpcEndpoint(
            self,
            "SQSEndpoint",
            vpc=self.vpc,
            service=ec2.InterfaceVpcEndpointAwsService.SQS,
            open=True,
            private_dns_enabled=True,
        )
        # Save useful info in SSM for later usage
        ssm.StringParameter(
            self,
            "VpcIdParam",
            parameter_name=f"/{scope.stage_name}/VpcId",
            string_value=self.vpc.vpc_id,
        )
        self.task_subnets = ssm.StringListParameter(
            self,
            "VpcPrivateSubnetsParam",
            parameter_name=f"/{scope.stage_name}/VpcPrivateSubnetsParam",
            string_list_value=[
                s.subnet_id
                for s in self.vpc.select_subnets(
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
                ).subnets
            ],
        )
