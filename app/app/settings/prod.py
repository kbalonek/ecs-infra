""" Production Settings """
from .stage import PRIVATE_IP
from .stage import *

 
# Set to your Domain here
ALLOWED_HOSTS = [
    "testmaker.balonek.pl",
    "www.testmaker.balonek.pl",
]

if PRIVATE_IP:
    ALLOWED_HOSTS.append(PRIVATE_IP)

print("ALLOWED_HOSTS (prod): ", ALLOWED_HOSTS)
