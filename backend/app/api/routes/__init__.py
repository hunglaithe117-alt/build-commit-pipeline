"""API router aggregator."""

from fastapi import APIRouter

from app.api.routes import data_sources, dead_letters, jobs, outputs, sonar

api_router = APIRouter()
api_router.include_router(data_sources.router, prefix="/data-sources", tags=["data-sources"])
api_router.include_router(dead_letters.router, prefix="/dead-letters", tags=["dead-letters"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(sonar.router, prefix="/sonar", tags=["sonar"])
api_router.include_router(outputs.router, prefix="/outputs", tags=["outputs"])
