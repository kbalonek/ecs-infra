sql = """
CREATE DATABASE demo_db;
CREATE USER demo_user WITH PASSWORD '{{resolve:secretsmanager:/demo/DatabaseCredentials:SecretString:password}}';
GRANT ALL PRIVILEGES ON DATABASE demo_db TO demo_user;
\c demo_db
GRANT ALL ON SCHEMA public TO demo_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO demo_user;
GRANT ALL ON ALL TABLES IN SCHEMA public TO demo_user;
"""

import boto3

# Initialize RDS Data client
rds_client = boto3.client('rds-data')

def execute_sql():
    # Replace these with your actual values
    cluster_arn = 'your-cluster-arn'
    secret_arn = 'arn:aws:secretsmanager:eu-west-2:985539802361:secret:RDSSecret3683CA93-GyJpUaLIrNNw-ScZi1g'
    database = 'postgres'  # Use postgres database for all commands

    try:
        response = rds_client.execute_statement(
            resourceArn=cluster_arn,
            secretArn=secret_arn,
            database=database,
            sql=sql  # Use the existing sql variable that contains all commands
        )
        print("Successfully executed all SQL commands")
        print(response)
        
    except rds_client.exceptions.BadRequestException as e:
        print(f"Error executing SQL commands")
        print(f"Error message: {str(e)}")
        raise

if __name__ == "__main__":
    execute_sql()
