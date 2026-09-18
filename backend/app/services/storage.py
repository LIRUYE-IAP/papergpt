import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from fastapi import UploadFile

CHUNK_SIZE = 1024 * 1024


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
