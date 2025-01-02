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
            domain_name: str,
            **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.hosted_zone = route53.HostedZone.from_lookup(
            self,
            "HostedZone",
            domain_name=domain_name
        )
        self.dns_record = route53.ARecord(
            self,
            "ARecord",
            zone=self.hosted_zone,
            # if the subdomain is already included in the hosted zone root, we don't need to append it again
            # record_name=subdomain,
            target=route53.RecordTarget.from_alias(targets.LoadBalancerTarget(alb))
        )
