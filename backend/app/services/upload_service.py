from __future__ import annotations

import os
from pathlib import Path
import uuid

import aiofiles
from fastapi import HTTPException, UploadFile, status
import magic

from app.config import settings


class UploadService:
    def __init__(self, upload_dir: str = settings.upload_dir):
        self.upload_dir = Path(upload_dir)

    async def save_image(self, file: UploadFile, subfolder: str, company_id: str) -> str:
        contents = await file.read()
        content_type = file.content_type or ""
        detected_type = magic.from_buffer(contents, mime=True)
        allowed_types = set(settings.allowed_image_types)

        if content_type not in allowed_types or detected_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported image type",
            )

        max_size = settings.max_file_size_mb * 1024 * 1024
        if len(contents) > max_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File exceeds maximum size",
            )

        suffix = Path(file.filename or "upload.bin").suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            suffix = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/webp": ".webp",
            }.get(detected_type, ".bin")

        target_dir = self.upload_dir / subfolder / company_id
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4()}{suffix}"
        target_path = target_dir / filename

        async with aiofiles.open(target_path, "wb") as buffer:
            await buffer.write(contents)

        return f"/uploads/{subfolder}/{company_id}/{filename}"

    async def delete_image(self, url: str) -> None:
        normalized = url.lstrip("/")
        if not normalized.startswith("uploads/"):
            return

        file_path = Path(normalized)
        if not file_path.is_absolute():
            file_path = Path(".") / file_path

        try:
            os.remove(file_path)
        except FileNotFoundError:
            return
        except OSError:
            return
