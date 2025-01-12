from aws_cdk import (
    CfnOutput,
    Stack,
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2,
    aws_certificatemanager as acm,
    aws_autoscaling as autoscaling,
)
from constructs import Construct

class LoadBalancerStack(Stack):
    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            vpc: ec2.Vpc,
            security_group: ec2.SecurityGroup,
            domain_certificate: acm.Certificate,
            auto_scaling_group: autoscaling.AutoScalingGroup,
            **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.auto_scaling_group = auto_scaling_group
        # Create ALB
        self.load_balancer = elbv2.ApplicationLoadBalancer(
            self, "LB",
            vpc=vpc,
            internet_facing=True,
            security_group=security_group
        )
        self.load_balancer.add_redirect()

        auto_scaling_group.connections.allow_from(
            self.load_balancer, 
            port_range=ec2.Port.tcp_range(32768, 65535), 
            description="allow incoming traffic from ALB",
        )

        # Create an empty target group as a placeholder
        # This will return 503s until real target groups are associated with the listener
        dummy_target_group = elbv2.ApplicationTargetGroup(
            self,
            "DummyTargetGroup",
            vpc=vpc,
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.INSTANCE,
            health_check=elbv2.HealthCheck(
                enabled=True, path="/", healthy_http_codes="200-299"
            ),
        )

        self.https_listener = self.load_balancer.add_listener(
            "PublicListener",
            protocol=elbv2.ApplicationProtocol.HTTPS,
            open=True,
            certificates=[domain_certificate],
            default_target_groups=[dummy_target_group],
        )

        CfnOutput(
            self, "LoadBalancerDNS",
            value="http://"+self.load_balancer.load_balancer_dns_name
        )
        # Output ALB and listener ARNs
        CfnOutput(
            self,
            "LoadBalancerArn", 
            value=self.load_balancer.load_balancer_arn,
            description="ARN of the Application Load Balancer",
            export_name=f"alb-listener-arn"
        )

        CfnOutput(
            self,
            "HttpsListenerArn",
            value=self.https_listener.listener_arn,
            description="ARN of the HTTPS listener"
        )
