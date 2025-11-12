from __future__ import annotations

import shutil
import uuid
import re
from pathlib import Path

import aiofiles
from fastapi import UploadFile

from app.core.config import settings
from typing import Optional


class LocalFileService:
    def __init__(self, base_upload_dir: Path | None = None) -> None:
        self.upload_dir = Path(base_upload_dir or settings.paths.uploads)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir = Path(settings.paths.exports)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        self.dead_letter_dir = Path(settings.paths.dead_letter)
        self.dead_letter_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir = self.upload_dir / "configs"
        self.config_dir.mkdir(parents=True, exist_ok=True)

    async def save_upload(self, upload: UploadFile) -> Path:
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

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
        slug = slug.strip("-")
        return slug or "default"

    def save_config_upload(
        self,
        upload: UploadFile,
        repo_key: Optional[str] = None,
        existing_path: Optional[str] = None,
    ) -> Path:
        if existing_path:
            target = Path(existing_path)
            target.parent.mkdir(parents=True, exist_ok=True)
        else:
            slug = self._slugify(repo_key) if repo_key else None
            base_dir = self.config_dir / slug if slug else self.config_dir
            base_dir.mkdir(parents=True, exist_ok=True)
            safe_name = upload.filename or "sonar.properties"
            target = base_dir / safe_name
        with target.open("wb") as out_file:
            for chunk in iter(lambda: upload.file.read(1024 * 1024), b""):
                out_file.write(chunk)
        upload.file.seek(0)
        return target


file_service = LocalFileService()
