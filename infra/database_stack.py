from aws_cdk import (
    Duration,
    Stack,
    aws_rds as rds,
    aws_ec2 as ec2,
    aws_ssm as ssm,
    aws_secretsmanager as secretsmanager,
    custom_resources
)
from constructs import Construct
import json


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
            engine=rds.DatabaseInstanceEngine.postgres(version=rds.PostgresEngineVersion.VER_16_4),
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

        # Create database and credentials for each app
        self.app_secrets = {}
        for app_config in self.apps_config:
            app_name = app_config['name']
            db_name = f"{app_name}_db"
            
            # Create database credentials
            db_creds = secretsmanager.Secret(
                self,
                f"{app_name}DBCredentials",
                secret_name=f"/{scope.stage_name}/{app_name}/DatabaseCredentials",
                generate_secret_string=secretsmanager.SecretStringGenerator(
                    secret_string_template=json.dumps({
                        "username": f"{app_name}_user",
                        "host": self.rds.instance_endpoint.hostname,
                        "port": str(self.rds.instance_endpoint.port),
                        "dbname": db_name,
                    }),
                    generate_string_key="password",
                    exclude_characters="/@\"",
                )
            )
            
            self.app_secrets[app_name] = db_creds

            # Store the secret name in SSM for reference
            ssm.StringParameter(
                self,
                f"{app_name}DBSecretNameParam",
                parameter_name=f"/{scope.stage_name}/{app_name}/DatabaseSecretNameParam",
                string_value=db_creds.secret_name,
            )

            # Create a custom resource to create the database and user
            custom_resources.AwsCustomResource(
                self,
                f"Create{app_name}Database",
                on_create=custom.AwsSdkCall(
                    service="RDS",
                    action="executeStatement",
                    parameters={
                        "resourceArn": self.rds.instance_arn,
                        "secretArn": self.rds.secret.secret_arn,
                        "database": "postgres",  # Connect to default db first
                        "sql": f"""
                            CREATE DATABASE {db_name};
                            CREATE USER {app_name}_user WITH PASSWORD '{{resolve:secretsmanager:{db_creds.secret_name}:SecretString:password}}';
                            GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {app_name}_user;
                        """
                    },
                    physical_resource_id=custom.PhysicalResourceId.of(f"{app_name}DBSetup")
                ),
                policy=custom.AwsCustomResourcePolicy.from_sdk_calls(
                    resources=[self.rds.instance_arn]
                )
            )
