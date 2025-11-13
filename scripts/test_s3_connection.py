#!/usr/bin/env python3
"""
Simple script to test S3 connection and configuration.

Usage:
    python scripts/test_s3_connection.py
"""

import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.core.config import settings
from app.services.s3_service import s3_service
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
LOG = logging.getLogger(__name__)


def test_s3_configuration():
    """Test S3 configuration."""
    LOG.info("=" * 60)
    LOG.info("S3 Configuration Test")
    LOG.info("=" * 60)
    
    LOG.info(f"S3 Enabled: {settings.s3.enabled}")
    
    if not settings.s3.enabled:
        LOG.warning("S3 is disabled in configuration")
        LOG.info("To enable S3, set 's3.enabled: true' in pipeline.yml")
        return False
    
    LOG.info(f"Bucket Name: {settings.s3.bucket_name}")
    LOG.info(f"Region: {settings.s3.region}")
    LOG.info(f"Endpoint URL: {settings.s3.endpoint_url or 'Default AWS'}")
    LOG.info(f"Sonar Logs Prefix: {settings.s3.sonar_logs_prefix}")
    LOG.info(f"Dead Letter Prefix: {settings.s3.dead_letter_prefix}")
    LOG.info(f"Error Logs Prefix: {settings.s3.error_logs_prefix}")
    
    if settings.s3.access_key_id:
        LOG.info(f"Access Key ID: {settings.s3.access_key_id[:10]}...") 
    else:
        LOG.info("Access Key ID: Using IAM role")
    
    return True


def test_s3_connection():
    """Test connection to S3."""
    LOG.info("")
    LOG.info("=" * 60)
    LOG.info("S3 Connection Test")
    LOG.info("=" * 60)
    
    if not s3_service.enabled:
        LOG.error("S3 service is not enabled")
        return False
    
    try:
        # Test by uploading a small test file
        test_content = "Test file - you can delete this"
        test_key = "test/connection_test.txt"
        
        LOG.info(f"Uploading test file to: s3://{s3_service.bucket_name}/{test_key}")
        
        success = s3_service.upload_text(
            content=test_content,
            s3_key=test_key
        )
        
        if not success:
            LOG.error("Failed to upload test file")
            return False
        
        LOG.info("✓ Upload successful")
        
        # Test if file exists
        LOG.info(f"Checking if file exists...")
        exists = s3_service.file_exists(test_key)
        
        if not exists:
            LOG.error("File was uploaded but cannot be found")
            return False
        
        LOG.info("✓ File verification successful")
        
        # Get S3 URL
        url = s3_service.get_s3_url(test_key)
        LOG.info(f"✓ S3 URL: {url}")
        
        LOG.info("")
        LOG.info("=" * 60)
        LOG.info("SUCCESS: S3 connection is working!")
        LOG.info("=" * 60)
        LOG.info(f"You can delete the test file with:")
        LOG.info(f"  aws s3 rm s3://{s3_service.bucket_name}/{test_key}")
        
        return True
        
    except Exception as e:
        LOG.error(f"Connection test failed: {e}")
        import traceback
        LOG.debug(traceback.format_exc())
        return False


def test_sonar_log_upload():
    """Test uploading a SonarQube log."""
    LOG.info("")
    LOG.info("=" * 60)
    LOG.info("SonarQube Log Upload Test")
    LOG.info("=" * 60)
    
    if not s3_service.enabled:
        LOG.error("S3 service is not enabled")
        return False
    
    try:
        test_log = """
[INFO] Scanner configuration file: /opt/sonar-scanner/conf/sonar-scanner.properties
[INFO] Project root configuration file: NONE
[INFO] SonarScanner 4.8.0.2856
[INFO] Java 11.0.17 Alpine (64-bit)
[INFO] Test log content - you can delete this
"""
        
        project_key = "test-project"
        commit_sha = "test123abc"
        instance_name = "test"
        
        LOG.info(f"Uploading test SonarQube log...")
        LOG.info(f"  Project: {project_key}")
        LOG.info(f"  Commit: {commit_sha}")
        LOG.info(f"  Instance: {instance_name}")
        
        s3_key = s3_service.upload_sonar_log(
            log_content=test_log,
            project_key=project_key,
            commit_sha=commit_sha,
            instance_name=instance_name
        )
        
        if not s3_key:
            LOG.error("Failed to upload SonarQube log")
            return False
        
        LOG.info(f"✓ Upload successful: {s3_key}")
        
        url = s3_service.get_s3_url(s3_key)
        LOG.info(f"✓ S3 URL: {url}")
        
        LOG.info("")
        LOG.info("You can delete the test file with:")
        LOG.info(f"  aws s3 rm s3://{s3_service.bucket_name}/{s3_key}")
        
        return True
        
    except Exception as e:
        LOG.error(f"SonarQube log upload test failed: {e}")
        import traceback
        LOG.debug(traceback.format_exc())
        return False


def main():
    LOG.info("Starting S3 connection tests...")
    LOG.info("")
    
    # Test 1: Configuration
    config_ok = test_s3_configuration()
    
    if not config_ok:
        LOG.error("Configuration test failed")
        sys.exit(1)
    
    # Test 2: Connection
    connection_ok = test_s3_connection()
    
    if not connection_ok:
        LOG.error("")
        LOG.error("=" * 60)
        LOG.error("FAILED: S3 connection test failed")
        LOG.error("=" * 60)
        LOG.error("")
        LOG.error("Troubleshooting steps:")
        LOG.error("1. Check your AWS credentials or IAM role")
        LOG.error("2. Verify the bucket name and region")
        LOG.error("3. Check network connectivity to S3")
        LOG.error("4. Verify IAM permissions for the bucket")
        LOG.error("")
        LOG.error("For more details, see: docs/S3_STORAGE_SETUP.md")
        sys.exit(1)
    
    # Test 3: SonarQube log upload
    sonar_ok = test_sonar_log_upload()
    
    if not sonar_ok:
        LOG.error("SonarQube log upload test failed")
        sys.exit(1)
    
    LOG.info("")
    LOG.info("=" * 60)
    LOG.info("ALL TESTS PASSED!")
    LOG.info("=" * 60)
    LOG.info("")
    LOG.info("Your S3 configuration is working correctly.")
    LOG.info("You can now start using S3 for log storage.")
    LOG.info("")


if __name__ == "__main__":
    main()
