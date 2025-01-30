
from constructs import Construct
from aws_cdk import (
    Stage,
)
from infra.domain_stack import DomainStack
from infra.network_stack import NetworkStack
from infra.database_stack import DatabaseStack
from infra.load_balancer_stack import LoadBalancerStack


class PipelineStage(Stage):

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        domain_name: str,
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
        )

        self.domain = DomainStack(
            self,
            "Domain",
            env=aws_env,
            domain_name=self.domain_name,
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
            domain_name=self.domain_name,
        )
