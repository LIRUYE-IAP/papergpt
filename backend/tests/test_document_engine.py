import json
from pathlib import Path

from app.core.config import settings
from tests.conftest import ApiClient
from tests.helpers import (
    academic_pdf_bytes,
    auth_headers,
    login_user,
    register_user,
    upload_pdf_bytes,
)


def authenticated_token(client: ApiClient, email: str) -> str:
    register_user(client, email)
    return login_user(client, email)


def upload_academic_paper(client: ApiClient, token: str) -> dict:
    return upload_pdf_bytes(
        client,
        token,
        academic_pdf_bytes(),
        "academic-layout.pdf",
    )


def flatten_outline(sections: list[dict]) -> list[dict]:
    flattened: list[dict] = []
    for section in sections:
        flattened.append(section)
        flattened.extend(flatten_outline(section["children"]))
    return flattened


def test_academic_pdf_parse_creates_sections_blocks_and_debug_json(
    client: ApiClient,
) -> None:
    token = authenticated_token(client, "parse@phase1.papergpt.dev")
    paper = upload_academic_paper(client, token)

    parse_response = client.post(
        f"/api/v1/papers/{paper['id']}/parse", headers=auth_headers(token)
    )
    outline_response = client.get(
        f"/api/v1/papers/{paper['id']}/outline", headers=auth_headers(token)
    )
    blocks_response = client.get(
        f"/api/v1/papers/{paper['id']}/blocks", headers=auth_headers(token)
    )

    assert parse_response.status_code == 200, parse_response.text
    parse_result = parse_response.json()
    assert parse_result["parse_status"] == "COMPLETED"
    assert parse_result["page_count"] == 3
    assert parse_result["section_count"] >= 5
    assert parse_result["block_count"] > parse_result["section_count"]

    assert outline_response.status_code == 200
    outline = flatten_outline(outline_response.json())
    titles = [section["title_original"] for section in outline]
    assert "1 Introduction" in titles
    assert "2 Methods" in titles
    assert "2.1 Data" in titles
    assert "References" in titles
    data_section = next(section for section in outline if section["title_original"] == "2.1 Data")
    methods_section = next(section for section in outline if section["title_original"] == "2 Methods")
    assert data_section["parent_id"] == methods_section["id"]

    assert blocks_response.status_code == 200
    blocks = blocks_response.json()
    reading_orders = [block["reading_order"] for block in blocks]
    assert reading_orders == sorted(reading_orders)
    assert len(reading_orders) == len(set(reading_orders))
    assert all({"x0", "y0", "x1", "y1"} <= block["bbox"].keys() for block in blocks)
    assert all("normalized" in block["bbox"] for block in blocks)
    block_types = {block["block_type"] for block in blocks}
    assert "FIGURE_CAPTION" in block_types
    assert "TABLE_CAPTION" in block_types
    reconstructed_text = " ".join(block["original_text"] for block in blocks)
    assert "forecasting" in reconstructed_text
    assert "fore- casting" not in reconstructed_text

    paper_root = Path(settings.storage_root) / Path(paper["file_key"]).parent.parent
    processing = paper_root / "processing"
    for filename in ("raw_pdf_blocks.json", "layout.json", "document.json"):
        artifact = processing / filename
        assert artifact.is_file()
        payload = json.loads(artifact.read_text(encoding="utf-8"))
        assert payload["metadata"]["page_count"] == 3
    document_json = json.loads((processing / "document.json").read_text(encoding="utf-8"))
    assert len(document_json["blocks"]) == len(blocks)
    assert len(document_json["sections"]) == len(outline)
    pages = {page["page_number"]: page for page in document_json["pages"]}
    for block in document_json["blocks"]:
        bbox = block["bbox"]
        normalized = bbox["normalized"]
        page = pages[block["page_number"]]
        assert 0 <= bbox["x0"] < bbox["x1"] <= page["width"]
        assert 0 <= bbox["y0"] < bbox["y1"] <= page["height"]
        assert 0 <= normalized["x0"] < normalized["x1"] <= 1
        assert 0 <= normalized["y0"] < normalized["y1"] <= 1
        assert block["metadata"]["page_width"] == page["width"]
        assert block["metadata"]["page_height"] == page["height"]
        assert page["coordinate_system"] == "PyMuPDF text-dict coordinates"


def test_double_column_reading_order_is_column_major(client: ApiClient) -> None:
    token = authenticated_token(client, "columns@phase1.papergpt.dev")
    paper = upload_academic_paper(client, token)
    parse_response = client.post(
        f"/api/v1/papers/{paper['id']}/parse", headers=auth_headers(token)
    )
    assert parse_response.status_code == 200, parse_response.text

    response = client.get(
        f"/api/v1/papers/{paper['id']}/blocks?page=1",
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    blocks = response.json()

    markers = ["LEFT ONE", "1.1 Motivation", "LEFT TWO", "RIGHT ONE", "RIGHT TWO"]
    marker_blocks = {
        marker: next(block for block in blocks if marker in block["original_text"])
        for marker in markers
    }
    assert [marker_blocks[marker]["column_index"] for marker in markers] == [0, 0, 0, 1, 1]
    assert [marker_blocks[marker]["reading_order"] for marker in markers] == sorted(
        marker_blocks[marker]["reading_order"] for marker in markers
    )
    assert marker_blocks["1.1 Motivation"]["block_type"] == "HEADING_2"


def test_headers_footers_page_numbers_and_references_are_not_translatable(
    client: ApiClient,
) -> None:
    token = authenticated_token(client, "classification@phase1.papergpt.dev")
    paper = upload_academic_paper(client, token)
    assert (
        client.post(
            f"/api/v1/papers/{paper['id']}/parse", headers=auth_headers(token)
        ).status_code
        == 200
    )
    blocks = client.get(
        f"/api/v1/papers/{paper['id']}/blocks", headers=auth_headers(token)
    ).json()

    marginalia = [
        block
        for block in blocks
        if block["block_type"] in {"HEADER", "FOOTER", "PAGE_NUMBER"}
    ]
    references = [block for block in blocks if block["block_type"] == "REFERENCE"]
    assert marginalia
    assert references
    assert all(not block["is_translatable"] for block in marginalia + references)


def test_reparse_replaces_results_without_duplicates(client: ApiClient) -> None:
    token = authenticated_token(client, "reparse@phase1.papergpt.dev")
    paper = upload_academic_paper(client, token)

    first = client.post(
        f"/api/v1/papers/{paper['id']}/parse", headers=auth_headers(token)
    )
    first_blocks = client.get(
        f"/api/v1/papers/{paper['id']}/blocks", headers=auth_headers(token)
    ).json()
    first_outline = flatten_outline(
        client.get(
            f"/api/v1/papers/{paper['id']}/outline", headers=auth_headers(token)
        ).json()
    )
    paper_root = Path(settings.storage_root) / Path(paper["file_key"]).parent.parent
    first_document = json.loads(
        (paper_root / "processing" / "document.json").read_text(encoding="utf-8")
    )
    second = client.post(
        f"/api/v1/papers/{paper['id']}/parse", headers=auth_headers(token)
    )
    second_blocks = client.get(
        f"/api/v1/papers/{paper['id']}/blocks", headers=auth_headers(token)
    ).json()
    second_outline = flatten_outline(
        client.get(
            f"/api/v1/papers/{paper['id']}/outline", headers=auth_headers(token)
        ).json()
    )
    second_document = json.loads(
        (paper_root / "processing" / "document.json").read_text(encoding="utf-8")
    )

    assert first.status_code == second.status_code == 200
    assert first.json()["block_count"] == second.json()["block_count"]
    assert len(first_blocks) == len(second_blocks)
    first_block_ids = [block["id"] for block in first_blocks]
    second_block_ids = [block["id"] for block in second_blocks]
    assert len(first_block_ids) == len(set(first_block_ids))
    assert first_block_ids == second_block_ids
    assert [section["id"] for section in first_outline] == [
        section["id"] for section in second_outline
    ]
    assert [block["id"] for block in first_document["blocks"]] == first_block_ids
    assert [block["id"] for block in second_document["blocks"]] == second_block_ids


def test_document_endpoints_enforce_ownership(client: ApiClient) -> None:
    owner_token = authenticated_token(client, "parse-owner@phase1.papergpt.dev")
    other_token = authenticated_token(client, "parse-other@phase1.papergpt.dev")
    paper = upload_academic_paper(client, owner_token)

    for method, suffix in (
        ("POST", "parse"),
        ("GET", "outline"),
        ("GET", "blocks"),
    ):
        response = client.request(
            method,
            f"/api/v1/papers/{paper['id']}/{suffix}",
            headers=auth_headers(other_token),
        )
        assert response.status_code == 404


def test_parse_failure_sets_failed_without_partial_results(client: ApiClient) -> None:
    token = authenticated_token(client, "parse-failure@phase1.papergpt.dev")
    paper = upload_pdf_bytes(client, token, b"%PDF-not-a-real-document", "broken.pdf")

    response = client.post(
        f"/api/v1/papers/{paper['id']}/parse", headers=auth_headers(token)
    )
    paper_response = client.get(
        f"/api/v1/papers/{paper['id']}", headers=auth_headers(token)
    )
    blocks_response = client.get(
        f"/api/v1/papers/{paper['id']}/blocks", headers=auth_headers(token)
    )

    assert response.status_code == 422
    assert paper_response.json()["parse_status"] == "FAILED"
    assert blocks_response.json() == []


def test_delete_parsed_paper_removes_original_and_processing_artifacts(
    client: ApiClient,
) -> None:
    token = authenticated_token(client, "delete-parsed@phase1.papergpt.dev")
    paper = upload_academic_paper(client, token)
    assert (
        client.post(
            f"/api/v1/papers/{paper['id']}/parse", headers=auth_headers(token)
        ).status_code
        == 200
    )
    paper_root = Path(settings.storage_root) / Path(paper["file_key"]).parent.parent
    assert (paper_root / "original" / "original.pdf").is_file()
    assert (paper_root / "processing" / "document.json").is_file()

    response = client.delete(
        f"/api/v1/papers/{paper['id']}", headers=auth_headers(token)
    )

    assert response.status_code == 204
    assert not paper_root.exists()
