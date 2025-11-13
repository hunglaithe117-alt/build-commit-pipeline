from __future__ import annotations
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router
from app.core.config import settings

# Configure logging from settings. `settings.logging.level` defaults to "INFO".
try:
    level_name = settings.logging.level
except Exception:
    level_name = "INFO"

# Resolve to a numeric level; fallback to INFO if unknown.
numeric_level = getattr(logging, str(level_name).upper(), logging.INFO)
logging.basicConfig(level=numeric_level)


app = FastAPI(
    title="Build Commit Pipeline",
    version="0.1.0",
    description="Pipeline orchestrator for TravisTorrent data ingestion and SonarQube enrichment.",
)

origins = {settings.web.base_url, "http://localhost:3000", "http://127.0.0.1:3000"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(origins),
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(api_router, prefix="/api")


@app.get("/health", tags=["health"])
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
