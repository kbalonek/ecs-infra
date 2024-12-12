""" Production Settings """
import logging
import requests
from .stage import *


logger = logging.getLogger(__name__)


# Set to your Domain here
ALLOWED_HOSTS = [
    "testmaker.balonek.pl",
    "www.testmaker.balonek.pl",
]
# The ALB uses the private IP when calling the health check endpoint
if os.environ.get("AWS_EXECUTION_ENV"):
    METADATA_URI = os.environ['ECS_CONTAINER_METADATA_URI']
    container_metadata = requests.get(METADATA_URI).json()
    logging.info("Container metadata", container_metadata)
    for network in container_metadata['Networks']:
        for ip_v4_address in network['IPv4Addresses']:
            ALLOWED_HOSTS.append(ip_v4_address)
logger.info("ALLOWED_HOSTS", ALLOWED_HOSTS)
