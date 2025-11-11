"""API router aggregator."""

from fastapi import APIRouter

from app.api.routes import data_sources, jobs, outputs, sonar

api_router = APIRouter()
api_router.include_router(data_sources.router, prefix="/data-sources", tags=["data-sources"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(sonar.router, prefix="/sonar", tags=["sonar"])
api_router.include_router(outputs.router, prefix="/outputs", tags=["outputs"])
