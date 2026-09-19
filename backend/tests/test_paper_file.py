import uuid

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


def test_authenticated_pdf_file_access(client: ApiClient) -> None:
    token = authenticated_token(client, "file-owner@phase1.papergpt.dev")
    paper = upload_pdf(client, token, "reader source.pdf")

    response = client.get(
        f"/api/v1/papers/{paper['id']}/file",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert response.content == MINIMAL_PDF
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-length"] == str(len(MINIMAL_PDF))
    assert "reader%20source.pdf" in response.headers["content-disposition"]
    assert "storage" not in response.headers["content-disposition"]


def test_pdf_file_requires_authentication(client: ApiClient) -> None:
    token = authenticated_token(client, "file-auth@phase1.papergpt.dev")
    paper = upload_pdf(client, token)

    response = client.get(f"/api/v1/papers/{paper['id']}/file")

    assert response.status_code == 401


def test_pdf_file_ownership_is_isolated(client: ApiClient) -> None:
    owner_token = authenticated_token(client, "file-private@phase1.papergpt.dev")
    other_token = authenticated_token(client, "file-other@phase1.papergpt.dev")
    paper = upload_pdf(client, owner_token)

    response = client.get(
        f"/api/v1/papers/{paper['id']}/file",
        headers=auth_headers(other_token),
    )

    assert response.status_code == 404


def test_missing_pdf_file_returns_not_found(client: ApiClient) -> None:
    token = authenticated_token(client, "file-missing@phase1.papergpt.dev")

    response = client.get(
        f"/api/v1/papers/{uuid.uuid4()}/file",
        headers=auth_headers(token),
    )

    assert response.status_code == 404


def test_pdf_file_supports_single_byte_ranges(client: ApiClient) -> None:
    token = authenticated_token(client, "file-range@phase1.papergpt.dev")
    paper = upload_pdf(client, token)

    response = client.get(
        f"/api/v1/papers/{paper['id']}/file",
        headers={**auth_headers(token), "Range": "bytes=0-7"},
    )

    assert response.status_code == 206
    assert response.content == MINIMAL_PDF[:8]
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-length"] == "8"
    assert response.headers["content-range"] == f"bytes 0-7/{len(MINIMAL_PDF)}"


def test_unsatisfiable_pdf_range_returns_416(client: ApiClient) -> None:
    token = authenticated_token(client, "file-bad-range@phase1.papergpt.dev")
    paper = upload_pdf(client, token)

    response = client.get(
        f"/api/v1/papers/{paper['id']}/file",
        headers={**auth_headers(token), "Range": "bytes=9999-"},
    )

    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{len(MINIMAL_PDF)}"
