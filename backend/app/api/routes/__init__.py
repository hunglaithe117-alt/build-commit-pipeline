"""API router aggregator."""

from fastapi import APIRouter

from app.api.routes import (
    failed_commits,
    fork_resolver,
    projects,
    scan_jobs,
    scan_results,
    sonar,
)

api_router = APIRouter()
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(failed_commits.router, prefix="/failed-commits", tags=["failed-commits"])
api_router.include_router(fork_resolver.router, prefix="/fork-resolver", tags=["fork-resolver"])
api_router.include_router(scan_jobs.router, prefix="/scan-jobs", tags=["scan-jobs"])
api_router.include_router(sonar.router, prefix="/sonar", tags=["sonar"])
api_router.include_router(scan_results.router, prefix="/scan-results", tags=["scan-results"])
