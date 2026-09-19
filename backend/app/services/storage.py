import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from fastapi import UploadFile

CHUNK_SIZE = 1024 * 1024
PROCESSING_ARTIFACTS = {
    "raw_pdf_blocks.json",
    "layout.json",
    "document.json",
}


class EmptyFileError(ValueError):
    pass


class FileTooLargeError(ValueError):
    pass


@dataclass(frozen=True)
class StoredPDF:
    file_key: str
    file_hash: str
    file_size: int


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _resolve_key(self, file_key: str) -> Path:
        normalized = PurePosixPath(file_key)
        if normalized.is_absolute() or ".." in normalized.parts:
            raise ValueError("Invalid storage key")
        path = (self.root / Path(*normalized.parts)).resolve()
        if path != self.root and self.root not in path.parents:
            raise ValueError("Storage key escapes the configured root")
        return path

    def path_for_key(self, file_key: str) -> Path:
        return self._resolve_key(file_key)

    def write_processing_json(
        self, file_key: str, filename: str, payload: object
    ) -> Path:
        if filename not in PROCESSING_ARTIFACTS:
            raise ValueError("Unsupported processing artifact")
        source_key = PurePosixPath(file_key)
        if len(source_key.parts) < 5:
            raise ValueError("Invalid paper file key")
        paper_key = source_key.parent.parent
        target = self._resolve_key((paper_key / "processing" / filename).as_posix())
        temporary = target.with_name(f".{target.name}.{uuid.uuid4()}.tmp")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return target

    def write_processing_artifacts(
        self, file_key: str, artifacts: dict[str, object]
    ) -> Path:
        if set(artifacts) != PROCESSING_ARTIFACTS:
            raise ValueError("A complete processing artifact set is required")
        source_key = PurePosixPath(file_key)
        if len(source_key.parts) < 5:
            raise ValueError("Invalid paper file key")
        paper_root = self._resolve_key(source_key.parent.parent.as_posix())
        processing = paper_root / "processing"
        operation_id = uuid.uuid4()
        staging = paper_root / f".processing.{operation_id}.tmp"
        backup = paper_root / f".processing.{operation_id}.backup"
        staging.mkdir(parents=True, exist_ok=False)

        try:
            for filename, payload in artifacts.items():
                (staging / filename).write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            if processing.exists():
                os.replace(processing, backup)
            try:
                os.replace(staging, processing)
            except Exception:
                if backup.exists():
                    os.replace(backup, processing)
                raise
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            if not processing.exists() and backup.exists():
                os.replace(backup, processing)
            raise
        finally:
            if backup.exists() and processing.exists():
                shutil.rmtree(backup, ignore_errors=True)

        return processing

    async def save_pdf(
        self,
        upload: UploadFile,
        user_id: uuid.UUID,
        paper_id: uuid.UUID,
        max_bytes: int,
    ) -> StoredPDF:
        file_key = (
            PurePosixPath("papers")
            / str(user_id)
            / str(paper_id)
            / "original"
            / "original.pdf"
        ).as_posix()
        target = self._resolve_key(file_key)
        temporary = target.with_name(f".{target.name}.uploading")
        target.parent.mkdir(parents=True, exist_ok=True)

        digest = hashlib.sha256()
        file_size = 0
        try:
            with temporary.open("wb") as output:
                while chunk := await upload.read(CHUNK_SIZE):
                    file_size += len(chunk)
                    if file_size > max_bytes:
                        raise FileTooLargeError
                    digest.update(chunk)
                    output.write(chunk)

            if file_size == 0:
                raise EmptyFileError
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            self._remove_empty_parents(target.parent)
            raise

        return StoredPDF(
            file_key=file_key,
            file_hash=digest.hexdigest(),
            file_size=file_size,
        )

    def delete_file(self, file_key: str) -> None:
        target = self._resolve_key(file_key)
        target.unlink(missing_ok=True)
        self._remove_empty_parents(target.parent)

    def stage_delete(self, file_key: str) -> str | None:
        source = self._resolve_key(file_key)
        if not source.exists():
            return None

        staged_key = (PurePosixPath(".trash") / f"{uuid.uuid4()}.pdf").as_posix()
        staged = self._resolve_key(staged_key)
        staged.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, staged)
        self._remove_empty_parents(source.parent)
        return staged_key

    def stage_delete_paper(self, file_key: str) -> tuple[str, str] | None:
        source_key = PurePosixPath(file_key).parent.parent.as_posix()
        source = self._resolve_key(source_key)
        if not source.exists():
            return None
        staged_key = (PurePosixPath(".trash") / str(uuid.uuid4())).as_posix()
        staged = self._resolve_key(staged_key)
        staged.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, staged)
        self._remove_empty_parents(source.parent)
        return staged_key, source_key

    def restore_staged_paper(self, staged_key: str, original_key: str) -> None:
        staged = self._resolve_key(staged_key)
        if not staged.exists():
            return
        original = self._resolve_key(original_key)
        original.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged, original)
        self._remove_empty_parents(staged.parent)

    def delete_tree(self, file_key: str) -> None:
        target = self._resolve_key(file_key)
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
        self._remove_empty_parents(target.parent)

    def restore_staged_file(self, staged_key: str, original_key: str) -> None:
        staged = self._resolve_key(staged_key)
        if not staged.exists():
            return
        original = self._resolve_key(original_key)
        original.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged, original)
        self._remove_empty_parents(staged.parent)

    def _remove_empty_parents(self, directory: Path) -> None:
        current = directory
        while current != self.root and self.root in current.parents:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent
