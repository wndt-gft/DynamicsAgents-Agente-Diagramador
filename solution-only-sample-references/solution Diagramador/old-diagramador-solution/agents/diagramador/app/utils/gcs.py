# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import datetime
from typing import Optional

import google.cloud.storage as storage
from google.api_core import exceptions


def create_bucket_if_not_exists(bucket_name: str, project: str, location: str) -> None:
    """Creates a new bucket if it doesn't already exist with public access enabled.

    Args:
        bucket_name: Name of the bucket to create
        project: Google Cloud project ID
        location: Location to create the bucket in (defaults to us-east5)
    """
    storage_client = storage.Client(project=project)

    if bucket_name.startswith("gs://"):
        bucket_name = bucket_name[5:]
    try:
        bucket = storage_client.get_bucket(bucket_name)
        logging.info(f"Bucket {bucket_name} already exists")

        # Ensure bucket has public access enabled (in case it exists but isn't public)
        try:
            _configure_bucket_public_access(bucket)
        except Exception as e:
            logging.warning(f"Could not configure public access on existing bucket: {e}")

    except exceptions.NotFound:
        # Create new bucket with public access
        bucket = storage_client.create_bucket(
            bucket_name,
            location=location,
            project=project,
        )
        logging.info(f"Created bucket {bucket.name} in {bucket.location}")

        # Configure public access on the newly created bucket
        try:
            _configure_bucket_public_access(bucket)
        except Exception as e:
            logging.warning(f"Could not configure public access on new bucket: {e}")


def _configure_bucket_public_access(bucket) -> None:
    """Configure bucket for public access by all users including unauthenticated.

    Args:
        bucket: GCS bucket object to configure
    """
    try:
        # First, try to disable uniform bucket-level access to allow object-level ACLs
        if bucket.iam_configuration.uniform_bucket_level_access_enabled:
            bucket.iam_configuration.uniform_bucket_level_access_enabled = False
            bucket.patch()
            logging.info(f"Disabled uniform bucket-level access for {bucket.name}")
    except Exception as e:
        logging.warning(f"Could not modify uniform bucket access: {e}")

    try:
        # Remove public access prevention (if any)
        bucket.iam_configuration.public_access_prevention = "inherited"
        bucket.patch()
        logging.info(f"Set public access prevention to inherited for bucket {bucket.name}")
    except Exception as e:
        logging.warning(f"Could not modify public access prevention: {e}")

    # Try multiple approaches for public access
    success = False

    # Approach 1: Try adding allUsers to IAM policy
    try:
        policy = bucket.get_iam_policy(requested_policy_version=3)

        # Check if allUsers already exists
        has_all_users = any(
            "allUsers" in binding.get("members", set())
            for binding in policy.bindings
        )

        if not has_all_users:
            policy.bindings.append({
                "role": "roles/storage.objectViewer",
                "members": {"allUsers"}
            })
            bucket.set_iam_policy(policy)
            logging.info(f"Added allUsers to IAM policy for bucket {bucket.name}")
            success = True
        else:
            logging.info(f"Bucket {bucket.name} already has allUsers access")
            success = True

    except Exception as e:
        logging.warning(f"Could not set IAM policy with allUsers: {e}")

    # Approach 2: Try adding allAuthenticatedUsers if allUsers failed
    if not success:
        try:
            policy = bucket.get_iam_policy(requested_policy_version=3)

            # Check if allAuthenticatedUsers already exists
            has_auth_users = any(
                "allAuthenticatedUsers" in binding.get("members", set())
                for binding in policy.bindings
            )

            if not has_auth_users:
                policy.bindings.append({
                    "role": "roles/storage.objectViewer",
                    "members": {"allAuthenticatedUsers"}
                })
                bucket.set_iam_policy(policy)
                logging.info(f"Added allAuthenticatedUsers to IAM policy for bucket {bucket.name}")
                success = True
            else:
                logging.info(f"Bucket {bucket.name} already has allAuthenticatedUsers access")
                success = True

        except Exception as e:
            logging.warning(f"Could not set IAM policy with allAuthenticatedUsers: {e}")

    # Approach 3: Set bucket default object ACL as fallback
    if not success:
        try:
            bucket.default_object_acl.all().grant_read()
            bucket.default_object_acl.save()
            logging.info(f"Set default object ACL to public for bucket {bucket.name}")
            success = True
        except Exception as e:
            logging.warning(f"Could not set default object ACL: {e}")

    if not success:
        logging.warning(f"Could not configure any form of public access for bucket {bucket.name}")
        # Don't raise error - continue with individual object public access


def upload_xml_to_gcs(xml_content: str, bucket_name: str = "diagram_signed_temp",
                      project: str = "gft-bu-gcp", filename: Optional[str] = None) -> str:
    """Uploads XML content to GCS bucket and returns the blob name.

    Args:
        xml_content: The XML content to upload
        bucket_name: GCS bucket name (defaults to diagram_signed_temp)
        project: Google Cloud project ID
        filename: Optional custom filename. If not provided, generates one with timestamp

    Returns:
        str: The blob name/path of the uploaded file

    Raises:
        Exception: If upload fails
    """
    try:
        storage_client = storage.Client(project=project)
        bucket = storage_client.bucket(bucket_name)

        # Generate filename if not provided
        if not filename:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"diagrams/{datetime.datetime.now().year:04d}/{datetime.datetime.now().month:02d}/diagrama_container_{timestamp}.xml"

        # Create blob and upload content
        blob = bucket.blob(filename)
        blob.upload_from_string(xml_content, content_type='application/xml')

        logging.info(f"XML uploaded to gs://{bucket_name}/{filename}")
        return filename

    except Exception as e:
        logging.error(f"Failed to upload XML to GCS: {e}")
        raise


def generate_signed_url(bucket_name: str, blob_name: str, project: str = "gft-bu-gcp",
                       expiration_hours: int = 24) -> str:
    """Generates a signed URL for public access to a GCS object.

    Args:
        bucket_name: GCS bucket name
        blob_name: Path/name of the blob in the bucket
        project: Google Cloud project ID
        expiration_hours: Hours until the URL expires (default 24)

    Returns:
        str: Signed URL for public access

    Raises:
        Exception: If URL generation fails
    """
    try:
        storage_client = storage.Client(project=project)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        # Try to generate signed URL with service account
        try:
            # Generate signed URL with expiration
            expiration = datetime.datetime.now() + datetime.timedelta(hours=expiration_hours)

            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=expiration,
                method="GET"
            )

            logging.info(f"Generated signed URL for gs://{bucket_name}/{blob_name}")
            return signed_url

        except Exception as sign_error:
            # Fallback to public URL if signing fails (when using user credentials)
            logging.warning(f"Could not generate signed URL: {sign_error}")
            logging.info("Falling back to public URL - ensuring blob is publicly accessible")

            # Make the blob publicly readable
            try:
                blob.make_public()
                logging.info(f"Made blob publicly accessible: gs://{bucket_name}/{blob_name}")
            except Exception as public_error:
                logging.warning(f"Could not make blob public: {public_error}")

            # Return public URL
            public_url = f"https://storage.googleapis.com/{bucket_name}/{blob_name}"
            logging.info(f"Generated public URL for gs://{bucket_name}/{blob_name}")
            return public_url

    except Exception as e:
        logging.error(f"Failed to generate URL: {e}")
        raise


def upload_and_get_signed_url(xml_content: str, bucket_name: str = "diagram_signed_temp",
                              project: str = "gft-bu-gcp", filename: Optional[str] = None,
                              expiration_hours: int = 24) -> tuple[str, str]:
    """Uploads XML to GCS and returns both the blob name and signed URL.

    Args:
        xml_content: The XML content to upload
        bucket_name: GCS bucket name (defaults to diagram_signed_temp)
        project: Google Cloud project ID
        filename: Optional custom filename
        expiration_hours: Hours until the URL expires (default 24)

    Returns:
        tuple: (blob_name, public_url)
    """
    try:
        # Ensure bucket exists
        create_bucket_if_not_exists(bucket_name, project, "us-east1")

        # Upload XML content
        blob_name = upload_xml_to_gcs(xml_content, bucket_name, project, filename)

        # Generate public URL (signed if possible, otherwise public)
        public_url = generate_signed_url(bucket_name, blob_name, project, expiration_hours)

        # Log detalhado do resultado
        logging.info(f"✅ GCS Upload successful:")
        logging.info(f"   - Bucket: {bucket_name}")
        logging.info(f"   - Blob: {blob_name}")
        logging.info(f"   - URL: {public_url[:100]}...")
        logging.info(f"   - Full path: gs://{bucket_name}/{blob_name}")

        # Retornar o caminho completo do GCS em vez de apenas o blob_name
        gcs_full_path = f"gs://{bucket_name}/{blob_name}"
        return gcs_full_path, public_url

    except Exception as e:
        logging.error(f"❌ GCS upload failed completely: {e}")
        # Retornar valores que indiquem falha mas permitam continuidade
        error_blob = f"upload_failed_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        error_url = f"Upload failed: {str(e)[:100]}"
        return error_blob, error_url
