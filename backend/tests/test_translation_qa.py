from sqlalchemy import func, select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.translation import Translation, TranslationQAResult, TranslationVersion
from app.services.translation_qa import (
    QA_FAILED,
    QA_PASSED,
    QA_WARNING,
    QACheck,
    aggregate_qa_status,
    evaluate_translation_qa,
)
from tests.conftest import ApiClient
from tests.helpers import (
    academic_pdf_bytes,
    auth_headers,
    login_user,
    register_user,
    upload_pdf_bytes,
)


def translated_paper(client: ApiClient, email: str) -> tuple[str, dict, list[dict]]:
    register_user(client, email)
    token = login_user(client, email)
    paper = upload_pdf_bytes(client, token, academic_pdf_bytes(), "qa.pdf")
    assert client.post(
        f"/api/v1/papers/{paper['id']}/parse",
        headers=auth_headers(token),
    ).status_code == 200
    response = client.post(
        f"/api/v1/papers/{paper['id']}/translate",
        headers=auth_headers(token),
        json={"target_language": "zh-CN"},
    )
    assert response.status_code == 200
    translations = client.get(
        f"/api/v1/papers/{paper['id']}/translations?target_language=zh-CN",
        headers=auth_headers(token),
    ).json()
    return token, paper, translations


def check_map(checks: list[QACheck]) -> dict[str, QACheck]:
    return {check.check_type: check for check in checks}


def test_translation_edit_cors_preflight_allows_patch(client: ApiClient) -> None:
    response = client.request(
        "OPTIONS",
        "/api/v1/papers/00000000-0000-0000-0000-000000000000/translations/"
        "00000000-0000-0000-0000-000000000000",
        headers={
            "Origin": settings.frontend_origin,
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert "PATCH" in response.headers["access-control-allow-methods"]


def test_deterministic_qa_scientific_consistency_checks(client: ApiClient) -> None:
    _, paper, translations = translated_paper(
        client, "qa-scientific@phase1.papergpt.dev"
    )
    with SessionLocal() as db:
        translation = db.get(Translation, translations[0]["id"])
        assert translation is not None
        cases = (
            ("The value was 850.", "该值为 851。", "NUMERIC_CONSISTENCY"),
            ("Pressure was 850 hPa.", "压力为 850 Pa。", "UNIT_CONSISTENCY"),
            ("Prior work [1–3] agrees.", "既有研究一致。", "CITATION_CONSISTENCY"),
            ("Figure 1 shows the result.", "图 1 展示结果。", "FIGURE_TABLE_CONSISTENCY"),
            ("O3 and NO2 increased.", "污染物增加。", "CHEMICAL_SPECIES_CONSISTENCY"),
            ("R² = 0.81 and p < 0.05.", "结果显著。", "STATISTICS_CONSISTENCY"),
        )
        for source, translated, expected_check in cases:
            translation.original_text = source
            translation.translated_text = translated
            checks = check_map(evaluate_translation_qa(db, translation))
            assert checks[expected_check].status == QA_FAILED


def test_qa_glossary_placeholder_empty_length_uncertainty_and_aggregation(
    client: ApiClient,
) -> None:
    token, paper, translations = translated_paper(
        client, "qa-rules@phase1.papergpt.dev"
    )
    glossary = client.post(
        "/api/v1/glossary",
        headers=auth_headers(token),
        json={
            "source_term": "Academic documents",
            "target_term": "学术文档",
            "source_language": "en",
            "target_language": "zh-CN",
            "scope": "PAPER",
            "paper_id": paper["id"],
            "case_sensitive": False,
            "enabled": True,
        },
    )
    assert glossary.status_code == 201

    with SessionLocal() as db:
        translation = db.get(Translation, translations[0]["id"])
        assert translation is not None

        translation.original_text = "Academic documents may improve results."
        translation.translated_text = "结果得到改善。"
        rules = check_map(evaluate_translation_qa(db, translation))
        assert rules["GLOSSARY_CONSISTENCY"].status == QA_WARNING
        assert rules["SCIENTIFIC_UNCERTAINTY"].status == QA_WARNING

        translation.original_text = "Normal source text."
        translation.translated_text = "__PAPERGPT_ABCDEF0123456789_TOKEN_0000__"
        rules = check_map(evaluate_translation_qa(db, translation))
        assert rules["PLACEHOLDER_INTEGRITY"].status == QA_FAILED

        translation.translated_text = ""
        rules = check_map(evaluate_translation_qa(db, translation))
        assert rules["COMPLETENESS"].status == QA_FAILED

        translation.translated_text = "译" * 500
        rules = check_map(evaluate_translation_qa(db, translation))
        assert rules["SUSPICIOUS_OUTPUT"].status == QA_WARNING

    assert aggregate_qa_status([]) == "PENDING"
    assert aggregate_qa_status([QACheck("A", QA_PASSED, "", {})]) == QA_PASSED
    assert aggregate_qa_status([QACheck("A", QA_WARNING, "", {})]) == QA_WARNING
    assert aggregate_qa_status(
        [QACheck("A", QA_WARNING, "", {}), QACheck("B", QA_FAILED, "", {})]
    ) == QA_FAILED


def test_qa_api_rerun_replaces_results(client: ApiClient) -> None:
    token, paper, translations = translated_paper(
        client, "qa-rerun@phase1.papergpt.dev"
    )
    selected = translations[0]
    first = client.get(
        f"/api/v1/papers/{paper['id']}/translations/{selected['id']}/qa",
        headers=auth_headers(token),
    )
    rerun_one = client.post(
        f"/api/v1/papers/{paper['id']}/translations/{selected['id']}/qa",
        headers=auth_headers(token),
    )
    rerun_two = client.post(
        f"/api/v1/papers/{paper['id']}/translations/{selected['id']}/qa",
        headers=auth_headers(token),
    )
    assert first.status_code == rerun_one.status_code == rerun_two.status_code == 200
    assert len(first.json()["results"]) == 11
    assert len(rerun_one.json()["results"]) == len(rerun_two.json()["results"]) == 11
    assert len({item["check_type"] for item in rerun_two.json()["results"]}) == 11
    with SessionLocal() as db:
        count = db.scalar(
            select(func.count(TranslationQAResult.id)).where(
                TranslationQAResult.translation_id == selected["id"]
            )
        )
    assert count == 11


def test_translation_edit_versions_qa_and_reparse_preservation(
    client: ApiClient,
) -> None:
    token, paper, translations = translated_paper(
        client, "translation-edit@phase1.papergpt.dev"
    )
    selected = translations[0]
    versions_before = client.get(
        f"/api/v1/papers/{paper['id']}/translations/{selected['id']}/versions",
        headers=auth_headers(token),
    ).json()
    qa_before = client.get(
        f"/api/v1/papers/{paper['id']}/translations/{selected['id']}/qa",
        headers=auth_headers(token),
    ).json()
    manual_text = "人工校订的完整学术译文。"
    edit = client.request(
        "PATCH",
        f"/api/v1/papers/{paper['id']}/translations/{selected['id']}",
        headers=auth_headers(token),
        json={"translated_text": manual_text},
    )
    assert edit.status_code == 200, edit.text
    assert edit.json()["translated_text"] == manual_text
    assert edit.json()["user_modified"] is True
    assert edit.json()["qa_status"] != "PENDING"

    versions_after = client.get(
        f"/api/v1/papers/{paper['id']}/translations/{selected['id']}/versions",
        headers=auth_headers(token),
    ).json()
    qa_after = client.get(
        f"/api/v1/papers/{paper['id']}/translations/{selected['id']}/qa",
        headers=auth_headers(token),
    ).json()
    assert len(versions_before) == 1
    assert len(versions_after) == 2
    assert versions_after[0]["id"] == versions_before[0]["id"]
    assert [version["version_number"] for version in versions_after] == [1, 2]
    assert versions_after[-1]["reason"] == "USER_EDIT"
    assert versions_after[-1]["provider"] == "user"
    assert {item["id"] for item in qa_after["results"]}.isdisjoint(
        {item["id"] for item in qa_before["results"]}
    )

    assert client.post(
        f"/api/v1/papers/{paper['id']}/parse",
        headers=auth_headers(token),
    ).status_code == 200
    translation_after_reparse = next(
        item
        for item in client.get(
            f"/api/v1/papers/{paper['id']}/translations?target_language=zh-CN",
            headers=auth_headers(token),
        ).json()
        if item["id"] == selected["id"]
    )
    versions_after_reparse = client.get(
        f"/api/v1/papers/{paper['id']}/translations/{selected['id']}/versions",
        headers=auth_headers(token),
    ).json()
    assert translation_after_reparse["translated_text"] == manual_text
    assert translation_after_reparse["user_modified"] is True
    assert [item["id"] for item in versions_after_reparse] == [
        item["id"] for item in versions_after
    ]


def test_translation_edit_validation_and_ownership(client: ApiClient) -> None:
    owner_token, paper, translations = translated_paper(
        client, "translation-edit-owner@phase1.papergpt.dev"
    )
    register_user(client, "translation-edit-other@phase1.papergpt.dev")
    other_token = login_user(client, "translation-edit-other@phase1.papergpt.dev")
    selected = translations[0]
    path = f"/api/v1/papers/{paper['id']}/translations/{selected['id']}"

    assert client.request(
        "PATCH",
        path,
        headers=auth_headers(owner_token),
        json={"translated_text": "   "},
    ).status_code == 422
    assert client.request(
        "PATCH",
        path,
        headers=auth_headers(other_token),
        json={"translated_text": "越权修改"},
    ).status_code == 404
    assert client.get(
        f"{path}/versions", headers=auth_headers(other_token)
    ).status_code == 404
    assert client.get(
        f"{path}/qa", headers=auth_headers(other_token)
    ).status_code == 404
    assert client.post(
        f"{path}/qa", headers=auth_headers(other_token)
    ).status_code == 404
