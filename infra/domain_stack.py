from aws_cdk import (
    Stack,
    aws_route53 as route53,
    aws_certificatemanager as acm,
)
from constructs import Construct


class DomainStack(Stack):

    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            domain_name: str,
            subdomain: str,
            **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # We will include the subdomain in the zone name as we are using hosted zone delegation (i.e. the zone for the domain_name is in another account)
        domain_name = f"{subdomain}.{domain_name}"
        # Create a Route53 hosted zone for the subdomain (the root zone is managed by Route53 in another account and needs to be updated manually)
        self.hosted_zone = route53.HostedZone(
            self,
            "HostedZone",
            zone_name=domain_name,
        )

        # Create a certificate for the subdomain
        self.certificate = acm.Certificate(self, "Certificate",
            domain_name=domain_name,
            validation=acm.CertificateValidation.from_dns(self.hosted_zone)
        )
