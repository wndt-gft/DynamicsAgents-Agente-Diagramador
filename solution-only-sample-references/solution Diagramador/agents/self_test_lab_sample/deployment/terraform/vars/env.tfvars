# Project name used for resource naming
project_name = "self-test-lab"

# Your Production Google Cloud project id
prod_project_id = "gft-bu-gcp"

# Your Staging / Test Google Cloud project id
staging_project_id = "gft-bu-gcp"

# Your Google Cloud project ID that will be used to host the Cloud Build pipelines.
cicd_runner_project_id = "gft-bu-gcp"
# Name of the host connection you created in Cloud Build
host_connection_name = "self-test-lab-github-connection"

# Name of the repository you added to Cloud Build
repository_name = "self-test-lab"
repository_owner = "gft-technologies"

# The Google Cloud region you will use to deploy the infrastructure
region = "us-east5"

# Cloud Build Connection
create_cb_connection = true
