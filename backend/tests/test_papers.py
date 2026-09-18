from pathlib import Path

from app.core.config import settings
from tests.conftest import ApiClient
from tests.helpers import (
    MINIMAL_PDF,
    auth_headers,
    login_user,
    register_user,
    upload_pdf,
)


def authenticated_token(client: ApiClient, email: str) -> str:
    register_user(client, email)
    return login_user(client, email)


def test_pdf_upload_success(client: ApiClient) -> None:
    token = authenticated_token(client, "upload@phase1.papergpt.dev")
    paper = upload_pdf(client, token, "research.pdf")

    assert paper["original_filename"] == "research.pdf"
    assert paper["filename"] == "original.pdf"
    assert paper["file_size"] == len(MINIMAL_PDF)
    assert len(paper["file_hash"]) == 64
    assert paper["parse_status"] == "NOT_STARTED"
    assert paper["translation_status"] == "NOT_STARTED"
    assert paper["qa_status"] == "PENDING"
    assert (Path(settings.storage_root) / Path(paper["file_key"])).is_file()


def test_non_pdf_is_rejected(client: ApiClient) -> None:
    token = authenticated_token(client, "non-pdf@phase1.papergpt.dev")

    response = client.post(
        "/api/v1/papers",
        headers=auth_headers(token),
        files={"file": ("notes.txt", b"not a pdf", "text/plain")},
    )

    assert response.status_code == 415


def test_empty_pdf_is_rejected(client: ApiClient) -> None:
    token = authenticated_token(client, "empty@phase1.papergpt.dev")

    response = client.post(
        "/api/v1/papers",
        headers=auth_headers(token),
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )

    assert response.status_code == 400


def test_fake_pdf_signature_is_rejected(client: ApiClient) -> None:
    token = authenticated_token(client, "fake-pdf@phase1.papergpt.dev")

    response = client.post(
        "/api/v1/papers",
        headers=auth_headers(token),
        files={"file": ("fake.pdf", b"This is not a PDF", "application/pdf")},
    )

    assert response.status_code == 415
    assert response.json() == {
        "detail": "File content does not have a valid PDF signature"
    }


def test_list_and_detail_papers(client: ApiClient) -> None:
    token = authenticated_token(client, "library@phase1.papergpt.dev")
    uploaded = upload_pdf(client, token)

    list_response = client.get("/api/v1/papers", headers=auth_headers(token))
    detail_response = client.get(
        f"/api/v1/papers/{uploaded['id']}", headers=auth_headers(token)
    )

    assert list_response.status_code == 200
    assert [paper["id"] for paper in list_response.json()] == [uploaded["id"]]
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == uploaded["id"]
    assert detail_response.json()["last_opened_at"] is not None


def test_delete_paper_removes_database_record_and_file(client: ApiClient) -> None:
    token = authenticated_token(client, "delete@phase1.papergpt.dev")
    uploaded = upload_pdf(client, token)
    stored_path = Path(settings.storage_root) / Path(uploaded["file_key"])
    assert stored_path.is_file()

    delete_response = client.delete(
        f"/api/v1/papers/{uploaded['id']}", headers=auth_headers(token)
    )
    detail_response = client.get(
        f"/api/v1/papers/{uploaded['id']}", headers=auth_headers(token)
    )

    assert delete_response.status_code == 204
    assert detail_response.status_code == 404
    assert not stored_path.exists()


def test_user_ownership_is_enforced(client: ApiClient) -> None:
    owner_token = authenticated_token(client, "owner@phase1.papergpt.dev")
    other_token = authenticated_token(client, "other@phase1.papergpt.dev")
    uploaded = upload_pdf(client, owner_token, "private.pdf")

    get_response = client.get(
        f"/api/v1/papers/{uploaded['id']}", headers=auth_headers(other_token)
    )
    delete_response = client.delete(
        f"/api/v1/papers/{uploaded['id']}", headers=auth_headers(other_token)
    )
    owner_response = client.get(
        f"/api/v1/papers/{uploaded['id']}", headers=auth_headers(owner_token)
    )

    assert get_response.status_code == 404
    assert delete_response.status_code == 404
    assert owner_response.status_code == 200
