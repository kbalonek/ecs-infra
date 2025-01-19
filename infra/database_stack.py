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
            apps_config: list[dict],
            backup_retention_days: int = 1,
            **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.vpc = vpc
        self.backup_retention_days = backup_retention_days
        self.apps_config = apps_config

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
        self.rds.connections.allow_default_port_from_any_ipv4(
            description="Services in private subnets can access the DB"
        )

        # Create a dedicated security group for the DB init Lambda
        db_init_sg = ec2.SecurityGroup(
            self,
            "DBInitSecurityGroup",
            vpc=self.vpc,
            description="Security group for DB initialization Lambda function",
            allow_all_outbound=True,
        )

        # Allow ingress traffic from DB init Lambda to RDS
        self.rds.connections.allow_default_port_from(
            db_init_sg, description="DB initialization Lambda can access the DB"
        )

        # Create the provider that will be shared across all database initializations
        db_init_function = PythonFunction(
            self,
            "DBInitFunction",
            entry="infra/lambdas/db_init",
            runtime=lambda_.Runtime.PYTHON_3_11,
            timeout=Duration.minutes(5),
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[db_init_sg],
            # environment={
            #     "PYTHONPATH": "/var/runtime:/var/task/lib",
            # },
        )

        # Grant the Lambda function permissions to access RDS secrets
        self.rds.secret.grant_read(db_init_function)

        # Create the provider
        db_init_provider = custom_resources.Provider(
            self,
            "DBInitProvider",
            on_event_handler=db_init_function,
            log_retention=cdk.aws_logs.RetentionDays.ONE_WEEK
        )

        # Create database and credentials for each app
        self.database_secrets = {}
        for app_config in self.apps_config:
            app_name = app_config.name
            db_name = f"{app_name}_db"
            user_name = f"{app_name}_user"

            # Create database credentials
            database_secret = secretsmanager.Secret(
                self,
                f"{app_name}DBCredentials",
                secret_name=f"/{app_name}/DatabaseCredentials",
                generate_secret_string=secretsmanager.SecretStringGenerator(
                    secret_string_template=json.dumps({
                        "username": user_name,
                        "host": self.rds.instance_endpoint.hostname,
                        "port": str(self.rds.instance_endpoint.port),
                        "dbname": db_name,
                    }),
                    generate_string_key="password",
                    exclude_characters="/@\"",
                )
            )
            self.database_secrets[app_name] = database_secret

            # Grant the Lambda function permissions to access app secrets
            database_secret.grant_read(db_init_function)

            CfnOutput(
                self,
                f"{app_name}DatabaseSecretName",
                value=database_secret.secret_name,
                description=f"Secret name for {app_name} database credentials",
                export_name=f"{app_name}-db-secret-name"
            )

            # Store the secret name in SSM for reference
            ssm.StringParameter(
                self,
                f"{app_name}DBSecretNameParam",
                parameter_name=f"/{app_name}/DatabaseSecretNameParam",
                string_value=database_secret.secret_name,
            )

        for app_config in self.apps_config:
            app_name = app_config.name
            # Create the custom resource using the provider
            custom_resource = CustomResource(
                self,
                f"{app_name}DbInitCustomResource",
                resource_type="Custom::DBInit",
                service_token=db_init_provider.service_token,
                properties={
                    "adminSecretArn": self.rds.secret.secret_arn,
                    "appSecretArn": self.database_secrets[app_name].secret_arn,
                },
            )
            custom_resource.node.add_dependency(self.rds)
            custom_resource.node.add_dependency(self.database_secrets[app_name])
