#!/usr/bin/env python3
"""
Script to migrate existing logs from local storage to S3.

Usage:
    python scripts/migrate_logs_to_s3.py [--dry-run] [--delete-local]
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.core.config import settings
from app.services.s3_service import s3_service
from app.services import repository
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOG = logging.getLogger(__name__)


def migrate_sonar_logs(dry_run: bool = False, delete_local: bool = False):
    """Migrate SonarQube scan logs to S3."""
    LOG.info("Starting migration of SonarQube logs to S3...")
    
    if not s3_service.enabled:
        LOG.error("S3 service is not enabled. Please enable it in pipeline.yml")
        return
    
    base_dir = Path(settings.paths.default_workdir)
    if not base_dir.exists():
        LOG.warning(f"Work directory does not exist: {base_dir}")
        return
    
    # Find all log files: {base_dir}/{instance}/{project}/logs/{commit}.log
    log_files = list(base_dir.glob("*/*/logs/*.log"))
    
    LOG.info(f"Found {len(log_files)} log files to migrate")
    
    uploaded_count = 0
    failed_count = 0
    skipped_count = 0
    
    for log_file in log_files:
        try:
            # Parse path: instance/project/logs/commit.log
            parts = log_file.parts
            if len(parts) < 5:
                LOG.warning(f"Invalid path structure: {log_file}")
                continue
                
            instance_name = parts[-4]
            project_key = parts[-3]
            commit_sha = log_file.stem
            
            s3_key = (
                f"{settings.s3.sonar_logs_prefix}/{instance_name}/"
                f"{project_key}/{commit_sha}.log"
            )
            
            # Check if already exists in S3
            if s3_service.file_exists(s3_key):
                LOG.debug(f"Already exists in S3: {s3_key}")
                skipped_count += 1
                continue
            
            if dry_run:
                LOG.info(f"[DRY RUN] Would upload: {log_file} -> {s3_key}")
                uploaded_count += 1
                continue
            
            # Read and upload
            content = log_file.read_text(encoding='utf-8')
            
            success = s3_service.upload_sonar_log(
                log_content=content,
                project_key=project_key,
                commit_sha=commit_sha,
                instance_name=instance_name
            )
            
            if success:
                LOG.info(f"Uploaded: {log_file} -> {s3_key}")
                uploaded_count += 1
                
                # Update database with S3 key
                try:
                    # Find the sonar run for this commit
                    component_key = f"{project_key}_{commit_sha}"
                    run = repository.find_sonar_run_by_component(component_key)
                    
                    if run:
                        repository.upsert_sonar_run(
                            data_source_id=run.get('data_source_id'),
                            project_key=project_key,
                            commit_sha=commit_sha,
                            job_id=run.get('job_id'),
                            s3_log_key=s3_key,
                        )
                        LOG.debug(f"Updated database for {component_key}")
                except Exception as e:
                    LOG.warning(f"Failed to update database for {component_key}: {e}")
                
                # Delete local file if requested
                if delete_local:
                    log_file.unlink()
                    LOG.info(f"Deleted local file: {log_file}")
            else:
                LOG.error(f"Failed to upload: {log_file}")
                failed_count += 1
                
        except Exception as e:
            LOG.error(f"Error processing {log_file}: {e}")
            failed_count += 1
    
    LOG.info(f"""
Migration Summary:
------------------
Total files found: {len(log_files)}
Uploaded: {uploaded_count}
Skipped (already in S3): {skipped_count}
Failed: {failed_count}
    """)


def migrate_dead_letters(dry_run: bool = False, delete_local: bool = False):
    """Migrate dead letter files to S3."""
    LOG.info("Starting migration of dead letter files to S3...")
    
    if not s3_service.enabled:
        LOG.error("S3 service is not enabled. Please enable it in pipeline.yml")
        return
    
    dead_letter_dir = Path(settings.paths.dead_letter)
    if not dead_letter_dir.exists():
        LOG.warning(f"Dead letter directory does not exist: {dead_letter_dir}")
        return
    
    json_files = list(dead_letter_dir.glob("*.json"))
    
    LOG.info(f"Found {len(json_files)} dead letter files to migrate")
    
    uploaded_count = 0
    failed_count = 0
    skipped_count = 0
    
    for json_file in json_files:
        try:
            s3_key = f"{settings.s3.dead_letter_prefix}/{json_file.name}"
            
            if s3_service.file_exists(s3_key):
                LOG.debug(f"Already exists in S3: {s3_key}")
                skipped_count += 1
                continue
            
            if dry_run:
                LOG.info(f"[DRY RUN] Would upload: {json_file} -> {s3_key}")
                uploaded_count += 1
                continue
            
            content = json_file.read_text(encoding='utf-8')
            
            success = s3_service.upload_dead_letter(
                content=content,
                filename=json_file.name
            )
            
            if success:
                LOG.info(f"Uploaded: {json_file} -> {s3_key}")
                uploaded_count += 1
                
                if delete_local:
                    json_file.unlink()
                    LOG.info(f"Deleted local file: {json_file}")
            else:
                LOG.error(f"Failed to upload: {json_file}")
                failed_count += 1
                
        except Exception as e:
            LOG.error(f"Error processing {json_file}: {e}")
            failed_count += 1
    
    LOG.info(f"""
Dead Letter Migration Summary:
------------------------------
Total files found: {len(json_files)}
Uploaded: {uploaded_count}
Skipped (already in S3): {skipped_count}
Failed: {failed_count}
    """)


def main():
    parser = argparse.ArgumentParser(
        description="Migrate logs from local storage to S3"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be uploaded without actually uploading"
    )
    parser.add_argument(
        "--delete-local",
        action="store_true",
        help="Delete local files after successful upload (use with caution!)"
    )
    parser.add_argument(
        "--type",
        choices=["sonar", "dead-letters", "all"],
        default="all",
        help="Type of logs to migrate"
    )
    
    args = parser.parse_args()
    
    if args.delete_local and args.dry_run:
        LOG.error("Cannot use --delete-local with --dry-run")
        sys.exit(1)
    
    if args.delete_local:
        response = input(
            "WARNING: This will DELETE local files after upload. "
            "Are you sure? (yes/no): "
        )
        if response.lower() != "yes":
            LOG.info("Aborted by user")
            sys.exit(0)
    
    if args.dry_run:
        LOG.info("Running in DRY RUN mode - no changes will be made")
    
    if args.type in ["sonar", "all"]:
        migrate_sonar_logs(dry_run=args.dry_run, delete_local=args.delete_local)
    
    if args.type in ["dead-letters", "all"]:
        migrate_dead_letters(dry_run=args.dry_run, delete_local=args.delete_local)
    
    LOG.info("Migration completed!")


if __name__ == "__main__":
    main()
