from aws_cdk import (
    Stack,
    aws_autoscaling as autoscaling,
    aws_ec2 as ec2,
    aws_ssm as ssm,
    aws_ecs as ecs,
    aws_iam as iam,
    CfnOutput,
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
            nat_gateways=0,  # No Nat GWs are required as we will place instances in the public subnet
            enable_dns_hostnames=True,
            enable_dns_support=True,
        )
        CfnOutput(
            self,
            "VpcId", 
            value=self.vpc.vpc_id,
            description=f"ID of the VPC",
            export_name=f"vpc-id"
        )
        self.ecs_cluster = ecs.Cluster(self, f"ECSCluster", vpc=self.vpc)
        # Save useful values in in SSM
        self.ecs_cluster_name_param = ssm.StringParameter(
            self,
            "EcsClusterNameParam",
            parameter_name=f"/EcsClusterNameParam",
            string_value=self.ecs_cluster.cluster_name
        )

        # Export cluster name for cross-stack references
        CfnOutput(
            self,
            "EcsClusterName", 
            value=self.ecs_cluster.cluster_name,
            description=f"Name of the ECS cluster",
            export_name=f"ecs-cluster-name"
        )

        sg = ec2.SecurityGroup(
            self, 
            "sg",
            vpc=self.vpc,
        )
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "echo 'ECS_ENABLE_CONTAINER_METADATA=true' >> /etc/ecs/ecs.config"
        )

        # Warning - if you make any changes in the launch template, the changes
        # will be applied only after the EC2 instance is terminated & created anew
        launch_template = ec2.LaunchTemplate(
            self,
            "ASG-LaunchTemplate",
            instance_type=ec2.InstanceType("t3.micro"),
            machine_image=ecs.EcsOptimizedImage.amazon_linux2(),
            user_data=user_data,
            role=iam.Role(
                self,
                "InstanceRole",
                assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
                managed_policies=[
                    iam.ManagedPolicy.from_aws_managed_policy_name(
                        "service-role/AmazonEC2ContainerServiceforEC2Role"
                    ),
                    # Allow access to the instance with Session Manager
                    iam.ManagedPolicy.from_aws_managed_policy_name(
                        "AmazonSSMManagedInstanceCore"
                    ),
                ],
            ),
            security_group=sg,
        )

        self.auto_scaling_group = autoscaling.AutoScalingGroup(
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
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )

        capacity_provider = ecs.AsgCapacityProvider(
            self,
            "AsgCapacityProvider",
            auto_scaling_group=self.auto_scaling_group,
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
        # Save useful info in SSM for later usage
        ssm.StringParameter(
            self,
            "VpcIdParam",
            parameter_name=f"/VpcId",
            string_value=self.vpc.vpc_id,
        )
        self.task_subnets = ssm.StringListParameter(
            self,
            "VpcPublicSubnetsParam",
            parameter_name=f"/VpcPublicSubnetsParam",
            string_list_value=[
                s.subnet_id
                for s in self.vpc.select_subnets(
                    subnet_type=ec2.SubnetType.PUBLIC
                ).subnets
            ],
        )

        # Add ALB security group
        self.alb_security_group = ec2.SecurityGroup(
            self,
            "ALBSecurityGroup",
            vpc=self.vpc,
            description="Security group for Application Load Balancer",
            allow_all_outbound=True,
        )
        CfnOutput(
            self,
            "AlbSecurityGroupId",
            value=self.alb_security_group.security_group_id,
            description="Security group ID for Application Load Balancer",
            export_name=f"alb-security-group-id"
        )

        # Allow inbound HTTP/HTTPS
        self.alb_security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(80),
            "Allow HTTP traffic"
        )
        self.alb_security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(443),
            "Allow HTTPS traffic"
        )
