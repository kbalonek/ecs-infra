""" Production Settings """
import json
import logging
import time
from .stage import *


logger = logging.getLogger(__name__)

 
# Set to your Domain here
ALLOWED_HOSTS = [
    "testmaker.balonek.pl",
    "www.testmaker.balonek.pl",
]
# when running in ECS this will be set
metadata_file = os.environ.get("ECS_CONTAINER_METADATA_FILE")
if metadata_file: 
    ready = False
    attempts = 0
    max_attempts = 30  # 1 minute timeout
    print("Waiting for ECS metadata file to be ready...")
    
    while not ready and attempts < max_attempts:
        try:
            with open(metadata_file) as f:
                metadata = json.load(f)
                print("ECS metadata:", metadata)
                
                if metadata.get("MetadataFileStatus") == "READY":
                    ready = True
                    if "HostPrivateIPv4Address" in metadata:
                        private_ip = metadata["HostPrivateIPv4Address"]
                        ALLOWED_HOSTS.append(private_ip)
                        print("Found private IP:", private_ip)
                    else:
                        print("Warning: Private IP not found in ECS metadata file, ALB health checks may not work")
                else:
                    attempts += 1
                    time.sleep(2)
        except (IOError, json.JSONDecodeError) as e:
            print("Error reading ECS metadata file:", e)
            attempts += 1
            time.sleep(2)
    
    if not ready:
        print("Warning: Timed out waiting for ECS metadata file to be ready")

print("ALLOWED_HOSTS:", ALLOWED_HOSTS)
