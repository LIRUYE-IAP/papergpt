import uuid

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.document import Block
from app.models.paper import Paper
from app.services.glossary import match_glossary_terms
from app.services.translation_context import build_translation_context
from tests.conftest import ApiClient
from tests.helpers import (
    academic_pdf_bytes,
    auth_headers,
    login_user,
    register_user,
    upload_pdf_bytes,
)


def auth_token(client: ApiClient, email: str) -> str:
    register_user(client, email)
    return login_user(client, email)


def parsed_paper(client: ApiClient, token: str) -> dict:
    paper = upload_pdf_bytes(client, token, academic_pdf_bytes(), "glossary.pdf")
    response = client.post(
        f"/api/v1/papers/{paper['id']}/parse",
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    return paper


def create_term(
    client: ApiClient,
    token: str,
    *,
    source: str,
    target: str,
    scope: str,
    paper_id: str | None = None,
    case_sensitive: bool = False,
    enabled: bool = True,
):
    return client.post(
        "/api/v1/glossary",
        headers=auth_headers(token),
        json={
            "source_term": source,
            "target_term": target,
            "source_language": "en",
            "target_language": "zh-CN",
            "scope": scope,
            "paper_id": paper_id,
            "case_sensitive": case_sensitive,
            "enabled": enabled,
        },
    )


def test_paper_and_global_glossary_crud(client: ApiClient) -> None:
    token = auth_token(client, "glossary-crud@phase1.papergpt.dev")
    paper = parsed_paper(client, token)
    global_response = create_term(
        client,
        token,
        source="boundary layer",
        target="边界层",
        scope="USER_GLOBAL",
    )
    paper_response = create_term(
        client,
        token,
        source="Planetary boundary layer",
        target="行星边界层",
        scope="PAPER",
        paper_id=paper["id"],
    )
    assert global_response.status_code == paper_response.status_code == 201

    all_terms = client.get(
        "/api/v1/glossary", headers=auth_headers(token)
    ).json()
    paper_terms = client.get(
        f"/api/v1/papers/{paper['id']}/glossary",
        headers=auth_headers(token),
    ).json()
    assert {term["id"] for term in all_terms} == {
        global_response.json()["id"],
        paper_response.json()["id"],
    }
    assert {term["id"] for term in paper_terms} == {
        global_response.json()["id"],
        paper_response.json()["id"],
    }

    update = client.request(
        "PATCH",
        f"/api/v1/glossary/{paper_response.json()['id']}",
        headers=auth_headers(token),
        json={"target_term": "行星大气边界层", "case_sensitive": True},
    )
    assert update.status_code == 200
    assert update.json()["target_term"] == "行星大气边界层"
    assert update.json()["case_sensitive"] is True

    assert (
        client.delete(
            f"/api/v1/glossary/{paper_response.json()['id']}",
            headers=auth_headers(token),
        ).status_code
        == 204
    )
    assert (
        client.delete(
            f"/api/v1/glossary/{global_response.json()['id']}",
            headers=auth_headers(token),
        ).status_code
        == 204
    )
    assert client.get("/api/v1/glossary", headers=auth_headers(token)).json() == []


def test_glossary_duplicate_and_scope_validation(client: ApiClient) -> None:
    token = auth_token(client, "glossary-duplicate@phase1.papergpt.dev")
    first = create_term(
        client,
        token,
        source="Boundary Layer",
        target="边界层",
        scope="USER_GLOBAL",
    )
    duplicate = create_term(
        client,
        token,
        source="boundary layer",
        target="其他译法",
        scope="USER_GLOBAL",
    )
    invalid = create_term(
        client,
        token,
        source="invalid",
        target="无效",
        scope="PAPER",
    )
    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert invalid.status_code == 422


def test_glossary_ownership_isolation(client: ApiClient) -> None:
    owner_token = auth_token(client, "glossary-owner@phase1.papergpt.dev")
    other_token = auth_token(client, "glossary-other@phase1.papergpt.dev")
    paper = parsed_paper(client, owner_token)
    term = create_term(
        client,
        owner_token,
        source="document engine",
        target="文档引擎",
        scope="PAPER",
        paper_id=paper["id"],
    ).json()

    assert (
        client.get(
            f"/api/v1/papers/{paper['id']}/glossary",
            headers=auth_headers(other_token),
        ).status_code
        == 404
    )
    assert (
        create_term(
            client,
            other_token,
            source="stolen",
            target="越权",
            scope="PAPER",
            paper_id=paper["id"],
        ).status_code
        == 404
    )
    assert (
        client.request(
            "PATCH",
            f"/api/v1/glossary/{term['id']}",
            headers=auth_headers(other_token),
            json={"target_term": "越权修改"},
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/v1/glossary/{term['id']}",
            headers=auth_headers(other_token),
        ).status_code
        == 404
    )
    assert client.get("/api/v1/glossary", headers=auth_headers(other_token)).json() == []


def test_glossary_precedence_matching_and_context_integration(
    client: ApiClient,
) -> None:
    token = auth_token(client, "glossary-context@phase1.papergpt.dev")
    paper_data = parsed_paper(client, token)
    assert create_term(
        client,
        token,
        source="Academic documents",
        target="全局译法",
        scope="USER_GLOBAL",
    ).status_code == 201
    assert create_term(
        client,
        token,
        source="Academic documents",
        target="论文文档",
        scope="PAPER",
        paper_id=paper_data["id"],
    ).status_code == 201
    assert create_term(
        client,
        token,
        source="Academic",
        target="学术",
        scope="USER_GLOBAL",
    ).status_code == 201

    with SessionLocal() as db:
        paper = db.get(Paper, paper_data["id"])
        block = db.scalar(
            select(Block).where(
                Block.paper_id == paper_data["id"],
                Block.original_text.startswith("LEFT ONE"),
            )
        )
        assert paper is not None and block is not None
        context = build_translation_context(
            db,
            paper=paper,
            block=block,
            target_language="zh-CN",
        )
    assert context.glossary == {"Academic documents": "论文文档"}

    response = client.post(
        f"/api/v1/papers/{paper_data['id']}/blocks/{block.id}/translate",
        headers=auth_headers(token),
        json={"target_language": "zh-CN"},
    )
    assert response.status_code == 200
    translated = response.json()["translation"]["translated_text"]
    assert "Academic documents=论文文档" in translated
    assert "全局译法" not in translated


def test_longest_case_boundary_and_disabled_matching() -> None:
    from app.models.glossary import GlossaryTerm

    def term(source: str, *, case_sensitive: bool = False, enabled: bool = True):
        return GlossaryTerm(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            source_term=source,
            target_term=f"target:{source}",
            source_language="en",
            target_language="zh-CN",
            scope="USER_GLOBAL",
            case_sensitive=case_sensitive,
            enabled=enabled,
        )

    long_term = term("boundary layer height")
    short_overlap = term("boundary")
    insensitive = term("FORECASTING")
    sensitive = term("LEFT", case_sensitive=True)
    no_partial_word = term("column")
    disabled = term("reader", enabled=False)
    matched = match_glossary_terms(
        [long_term, short_overlap, insensitive, sensitive, no_partial_word, disabled],
        "The boundary layer height improves forecasting in left columns for a reader.",
    )
    matched_ids = {item.id for item in matched}
    assert long_term.id in matched_ids
    assert short_overlap.id not in matched_ids
    assert insensitive.id in matched_ids
    assert sensitive.id not in matched_ids
    assert no_partial_word.id not in matched_ids
    assert disabled.id not in matched_ids
