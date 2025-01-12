from typing import List
from aws_cdk import (
    Stack,
    aws_route53 as route53,
    aws_certificatemanager as acm,
    CfnOutput,
)
from constructs import Construct


class DomainStack(Stack):

    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            domain_name: str,
            subdomains: List[str],
            **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # We will include the subdomain in the zone name as we are using hosted zone delegation (i.e. the zone for the domain_name is in another account)
       
        # Create a Route53 hosted zone for the domain
        self.hosted_zone = route53.HostedZone.from_lookup(
            self,
            "HostedZone",
            domain_name=domain_name,
        )

        # Create a certificate for the subdomain
        self.certificate = acm.Certificate(self, "Certificate",
            domain_name=domain_name,
            # should we use a wildcard certificate?
            subject_alternative_names=[f"{subdomain}.{domain_name}" for subdomain in subdomains],
            validation=acm.CertificateValidation.from_dns(self.hosted_zone)
        )

        CfnOutput(
            self,
            "CertificateArn", 
            value=self.certificate.certificate_arn,
            description="ARN of the ACM certificate",
            export_name=f"certificate-arn"
        )
