from aws_cdk import (
    Stack,
    aws_route53 as route53,
    aws_route53_targets as targets,
    aws_elasticloadbalancingv2 as elbv2,
)
from constructs import Construct


class DnsRouteToAlbStack(Stack):

    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            alb: elbv2.ApplicationLoadBalancer,
            subdomain: str,
            hosted_zone: route53.HostedZone,
            **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.dns_record = route53.ARecord(
            self,
            "ARecord",
            zone=hosted_zone,
            # if the subdomain is already included in the hosted zone root, we don't need to append it again
            # record_name=subdomain,
            target=route53.RecordTarget.from_alias(targets.LoadBalancerTarget(alb))
        )
