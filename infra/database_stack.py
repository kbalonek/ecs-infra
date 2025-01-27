from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
    aws_rds as rds,
    aws_ec2 as ec2,
    aws_ssm as ssm,
    aws_secretsmanager as secretsmanager,
    aws_iam as iam,
    aws_lambda as lambda_,
    custom_resources,
    CustomResource,
)
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from constructs import Construct
import json
import aws_cdk as cdk


class DatabaseStack(Stack):

    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            vpc: ec2.Vpc,
            backup_retention_days: int = 1,
            **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.vpc = vpc
        self.backup_retention_days = backup_retention_days

        # Create the RDS instance
        self.rds = rds.DatabaseInstance(
            self,
            "RDS",
            engine=rds.DatabaseInstanceEngine.postgres(version=rds.PostgresEngineVersion.VER_17_2),
            vpc=self.vpc,
            storage_encrypted=True,
            allocated_storage=10,
            backup_retention=Duration.days(self.backup_retention_days),
            deletion_protection=True,
            instance_type=ec2.InstanceType("t4g.micro"),
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
        )

        # Allow ingress traffic from ECS tasks
        # TODO the ECS tasks are deployed to public subnets - where is access given?
        self.rds.connections.allow_default_port_from_any_ipv4(
            description="Services in private subnets can access the DB"
        )

        # Create a dedicated security group for the DB init Lambda
        self.db_init_sg = ec2.SecurityGroup(
            self,
            "DBInitSecurityGroup",
            vpc=self.vpc,
            description="Security group for DB initialization Lambda function",
            allow_all_outbound=True,
        )

        # Allow ingress traffic from DB init Lambda to RDS
        self.rds.connections.allow_default_port_from(
            self.db_init_sg, description="DB initialization Lambda can access the DB"
        )
