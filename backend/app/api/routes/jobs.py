from __future__ import annotations

from typing import List

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from app.models import Job
from app.services import repository

router = APIRouter()


@router.get("/", response_model=List[Job])
async def list_jobs() -> List[Job]:
    jobs = await run_in_threadpool(repository.list_jobs)
    return [Job(**job) for job in jobs]
