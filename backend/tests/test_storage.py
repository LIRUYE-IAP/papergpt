import json
import os
from pathlib import Path

import pytest

from app.services.storage import LocalStorage


def artifact_set(version: str) -> dict[str, object]:
    return {
        "raw_pdf_blocks.json": {"version": version, "kind": "raw"},
        "layout.json": {"version": version, "kind": "layout"},
        "document.json": {"version": version, "kind": "document"},
    }


def test_processing_artifacts_restore_previous_set_when_atomic_swap_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = LocalStorage(tmp_path)
    file_key = "papers/user-id/paper-id/original/original.pdf"
    original = storage.path_for_key(file_key)
    original.parent.mkdir(parents=True)
    original.write_bytes(b"%PDF-test")
    processing = storage.write_processing_artifacts(file_key, artifact_set("old"))

    real_replace = os.replace

    def fail_staging_promotion(source: str | Path, destination: str | Path) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        if source_path.name.endswith(".tmp") and destination_path.name == "processing":
            raise OSError("simulated artifact promotion failure")
        real_replace(source, destination)

    monkeypatch.setattr("app.services.storage.os.replace", fail_staging_promotion)

    with pytest.raises(OSError, match="simulated artifact promotion failure"):
        storage.write_processing_artifacts(file_key, artifact_set("new"))

    assert processing.is_dir()
    for filename in artifact_set("old"):
        payload = json.loads((processing / filename).read_text(encoding="utf-8"))
        assert payload["version"] == "old"
    assert not list(processing.parent.glob(".processing.*.tmp"))
    assert not list(processing.parent.glob(".processing.*.backup"))
