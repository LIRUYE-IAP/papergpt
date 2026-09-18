from tests.conftest import ApiClient

TEST_PASSWORD = "correct-horse-battery-staple"
MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"


def register_user(client: ApiClient, email: str, name: str = "Test User") -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": TEST_PASSWORD, "name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


def login_user(client: ApiClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def upload_pdf(client: ApiClient, token: str, filename: str = "paper.pdf") -> dict:
    response = client.post(
        "/api/v1/papers",
        headers=auth_headers(token),
        files={"file": (filename, MINIMAL_PDF, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()
