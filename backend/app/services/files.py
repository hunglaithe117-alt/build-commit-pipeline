from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import aiofiles
from fastapi import UploadFile

from app.core.config import settings


class LocalFileService:
    """Simple helper to persist uploads and read exported datasets."""

    def __init__(self, base_upload_dir: Path | None = None) -> None:
        self.upload_dir = Path(base_upload_dir or settings.paths.uploads)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir = Path(settings.paths.exports)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        self.dead_letter_dir = Path(settings.paths.dead_letter)
        self.dead_letter_dir.mkdir(parents=True, exist_ok=True)

    async def save_upload(self, upload: UploadFile) -> Path:
        suffix = Path(upload.filename or "dataset.csv").suffix or ".csv"
        target = self.upload_dir / f"{uuid.uuid4()}_{upload.filename}"
        async with aiofiles.open(target, "wb") as out_file:
            while chunk := await upload.read(1024 * 1024):
                await out_file.write(chunk)
        await upload.close()
        return target

    def copy_to_exports(self, source: Path, name: str | None = None) -> Path:
        destination = self.exports_dir / (name or source.name)
        shutil.copy2(source, destination)
        return destination

    def write_dead_letter(self, payload: str, identifier: str) -> Path:
        target = self.dead_letter_dir / f"{identifier}.json"
        target.write_text(payload, encoding="utf-8")
        return target


file_service = LocalFileService()
