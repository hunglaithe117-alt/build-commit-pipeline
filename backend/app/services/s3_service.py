"""S3 service for uploading logs and files to AWS S3."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings

LOG = logging.getLogger(__name__)


class S3Service:
    """Service for uploading logs to S3."""

    def __init__(self):
        self.enabled = settings.s3.enabled
        if not self.enabled:
            LOG.info("S3 service is disabled")
            return

        self.bucket_name = settings.s3.bucket_name
        self.region = settings.s3.region

        # Initialize S3 client
        session_kwargs = {
            "region_name": self.region,
        }

        if settings.s3.access_key_id and settings.s3.secret_access_key:
            session_kwargs["aws_access_key_id"] = settings.s3.access_key_id
            session_kwargs["aws_secret_access_key"] = settings.s3.secret_access_key

        self.session = boto3.Session(**session_kwargs)

        client_kwargs = {}
        if settings.s3.endpoint_url:
            client_kwargs["endpoint_url"] = settings.s3.endpoint_url

        self.s3_client = self.session.client("s3", **client_kwargs)

        LOG.info(
            "S3 service initialized: bucket=%s, region=%s",
            self.bucket_name,
            self.region,
        )

    def upload_file(
        self, file_path: Path, s3_key: str, content_type: Optional[str] = None
    ) -> bool:
        """
        Upload a file to S3.

        Args:
            file_path: Path to the local file
            s3_key: The S3 object key (path in S3)
            content_type: Optional content type for the file

        Returns:
            True if upload was successful, False otherwise
        """
        if not self.enabled:
            LOG.debug("S3 upload skipped (disabled): %s", file_path)
            return False

        if not file_path.exists():
            LOG.warning("File does not exist, cannot upload to S3: %s", file_path)
            return False

        try:
            extra_args = {}
            if content_type:
                extra_args["ContentType"] = content_type

            self.s3_client.upload_file(
                str(file_path), self.bucket_name, s3_key, ExtraArgs=extra_args
            )
            LOG.info("Uploaded %s to s3://%s/%s", file_path, self.bucket_name, s3_key)
            return True
        except ClientError as e:
            LOG.error("Failed to upload %s to S3: %s", file_path, e)
            return False

    def upload_text(
        self, content: str, s3_key: str, content_type: str = "text/plain"
    ) -> bool:
        """
        Upload text content directly to S3.

        Args:
            content: Text content to upload
            s3_key: The S3 object key (path in S3)
            content_type: Content type for the file

        Returns:
            True if upload was successful, False otherwise
        """
        if not self.enabled:
            LOG.debug("S3 upload skipped (disabled): %s", s3_key)
            return False

        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=content.encode("utf-8"),
                ContentType=content_type,
            )
            LOG.info("Uploaded text to s3://%s/%s", self.bucket_name, s3_key)
            return True
        except ClientError as e:
            LOG.error("Failed to upload text to S3 key %s: %s", s3_key, e)
            return False

    def upload_bytes(
        self, data: bytes, s3_key: str, content_type: str = "application/octet-stream"
    ) -> bool:
        """
        Upload bytes directly to S3.

        Args:
            data: Bytes data to upload
            s3_key: The S3 object key (path in S3)
            content_type: Content type for the file

        Returns:
            True if upload was successful, False otherwise
        """
        if not self.enabled:
            LOG.debug("S3 upload skipped (disabled): %s", s3_key)
            return False

        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name, Key=s3_key, Body=data, ContentType=content_type
            )
            LOG.info("Uploaded bytes to s3://%s/%s", self.bucket_name, s3_key)
            return True
        except ClientError as e:
            LOG.error("Failed to upload bytes to S3 key %s: %s", s3_key, e)
            return False

    def get_s3_url(self, s3_key: str) -> str:
        """
        Get the S3 URL for a given key.

        Args:
            s3_key: The S3 object key

        Returns:
            The S3 URL
        """
        if settings.s3.endpoint_url:
            # For custom endpoints (e.g., MinIO)
            return f"{settings.s3.endpoint_url}/{self.bucket_name}/{s3_key}"
        return f"s3://{self.bucket_name}/{s3_key}"

    def file_exists(self, s3_key: str) -> bool:
        """
        Check if a file exists in S3.

        Args:
            s3_key: The S3 object key

        Returns:
            True if file exists, False otherwise
        """
        if not self.enabled:
            return False

        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except ClientError:
            return False

    def upload_sonar_log(
        self,
        log_content: str,
        project_key: str,
        commit_sha: str,
        instance_name: str = "primary",
    ) -> Optional[str]:
        """
        Upload a SonarQube scan log to S3.

        Args:
            log_content: The log content to upload
            project_key: The project key
            commit_sha: The commit SHA
            instance_name: The SonarQube instance name

        Returns:
            The S3 key if successful, None otherwise
        """
        s3_key = (
            f"{settings.s3.sonar_logs_prefix}/{instance_name}/"
            f"{project_key}/{commit_sha}.log"
        )

        if self.upload_text(log_content, s3_key, content_type="text/plain"):
            return s3_key
        return None

    def upload_dead_letter(
        self, content: str, filename: str, content_type: str = "application/json"
    ) -> Optional[str]:
        """
        Upload a dead letter file to S3.

        Args:
            content: The content to upload
            filename: The filename
            content_type: Content type for the file

        Returns:
            The S3 key if successful, None otherwise
        """
        s3_key = f"{settings.s3.dead_letter_prefix}/{filename}"

        if self.upload_text(content, s3_key, content_type=content_type):
            return s3_key
        return None

    def upload_error_log(self, log_content: str, filename: str) -> Optional[str]:
        """
        Upload an error log to S3.

        Args:
            log_content: The log content to upload
            filename: The filename

        Returns:
            The S3 key if successful, None otherwise
        """
        s3_key = f"{settings.s3.error_logs_prefix}/{filename}"

        if self.upload_text(log_content, s3_key, content_type="text/plain"):
            return s3_key
        return None


# Global instance
s3_service = S3Service()
