from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


class RangeNotSatisfiable(ValueError):
    """Raised when a byte range cannot be served for a file."""


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int
    total: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1

    @property
    def content_range(self) -> str:
        return f"bytes {self.start}-{self.end}/{self.total}"


def parse_byte_range(value: str, file_size: int) -> ByteRange:
    """Parse one RFC 7233 byte range suitable for PDF.js."""

    if file_size <= 0 or not value.startswith("bytes="):
        raise RangeNotSatisfiable

    specification = value.removeprefix("bytes=").strip()
    if not specification or "," in specification or "-" not in specification:
        raise RangeNotSatisfiable

    start_text, end_text = specification.split("-", maxsplit=1)
    try:
        if not start_text:
            suffix_length = int(end_text)
            if suffix_length <= 0:
                raise RangeNotSatisfiable
            start = max(0, file_size - suffix_length)
            end = file_size - 1
        else:
            start = int(start_text)
            if start < 0 or start >= file_size:
                raise RangeNotSatisfiable
            end = file_size - 1 if not end_text else int(end_text)
            if end < start:
                raise RangeNotSatisfiable
            end = min(end, file_size - 1)
    except ValueError as exc:
        raise RangeNotSatisfiable from exc

    return ByteRange(start=start, end=end, total=file_size)


def iter_file_bytes(
    path: Path,
    *,
    start: int = 0,
    length: int | None = None,
    chunk_size: int = 1024 * 1024,
) -> Iterator[bytes]:
    """Yield a bounded file segment without exposing the local storage path."""

    with path.open("rb") as file_handle:
        file_handle.seek(start)
        remaining = length
        while remaining is None or remaining > 0:
            requested = chunk_size if remaining is None else min(chunk_size, remaining)
            chunk = file_handle.read(requested)
            if not chunk:
                break
            yield chunk
            if remaining is not None:
                remaining -= len(chunk)
