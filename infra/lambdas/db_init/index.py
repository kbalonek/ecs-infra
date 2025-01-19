import boto3
import psycopg
import json
from botocore.exceptions import ClientError
from typing import Any, Dict


def get_secret(secret_name: str) -> Dict[str, Any]:
    session = boto3.session.Session()
    client = session.client("secretsmanager")
    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        raise e
    else:
        if "SecretString" in get_secret_value_response:
            return json.loads(get_secret_value_response["SecretString"])
        else:
            raise Exception("SecretString not found in response")


def on_create(event: Dict[str, Any]) -> Dict[str, Any]:
    props = event["ResourceProperties"]
    admin_secret_arn = props["adminSecretArn"]
    app_secret_arn = props["appSecretArn"]

    # Get admin credentials
    admin_creds = get_secret(admin_secret_arn)
    app_creds = get_secret(app_secret_arn)

    # Connect to default database first
    with psycopg.connect(
        conninfo=(
            f"host={admin_creds['host']} "
            f"port={admin_creds['port']} "
            f"dbname=postgres "
            f"user={admin_creds['username']} "
            f"password={admin_creds['password']}"
        ),
        autocommit=True,
    ) as conn:
        with conn.cursor() as cur:
            # Create database and user
            cur.execute("CREATE DATABASE %s", [app_creds["dbname"]])
            cur.execute(
                "CREATE USER %s WITH PASSWORD %s",
                [app_creds["username"], app_creds["password"]],
            )
            cur.execute(
                "GRANT ALL PRIVILEGES ON DATABASE %s TO %s",
                [app_creds["dbname"], app_creds["username"]],
            )

    with psycopg.connect(
        conninfo=(
            f"host={app_creds['host']} "
            f"port={app_creds['port']} "
            f"dbname={app_creds['dbname']} "
            f"user={admin_creds['username']} "
            f"password={admin_creds['password']}"
        ),
        autocommit=True,
    ) as conn:

        with conn.cursor() as cur:
            cur.execute("GRANT ALL ON SCHEMA public TO %s", [app_creds["username"]])
            cur.execute(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO %s",
                [app_creds["username"]],
            )
            cur.execute(
                "GRANT ALL ON ALL TABLES IN SCHEMA public TO %s",
                [app_creds["username"]],
            )

    return {
        "PhysicalResourceId": f"{app_creds['dbname']}-setup",
        "Data": {
            "DatabaseName": app_creds["dbname"],
            "Username": app_creds["username"],
        },
    }


def on_update(event: Dict[str, Any]) -> Dict[str, Any]:
    return on_create(event)


def on_delete(event: Dict[str, Any]) -> Dict[str, Any]:
    # Optionally implement cleanup logic here
    # For now, we'll let RDS handle the cleanup when the instance is deleted
    return {"PhysicalResourceId": event["PhysicalResourceId"]}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    print(f"Received event: {json.dumps(event)}")

    request_type = event["RequestType"]
    if request_type == "Create":
        return on_create(event)
    elif request_type == "Update":
        return on_update(event)
    elif request_type == "Delete":
        return on_delete(event)
    else:
        raise Exception(f"Invalid request type: {request_type}")
