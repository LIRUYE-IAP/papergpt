from __future__ import annotations

from dataclasses import dataclass, field
import uuid

import pytest
from sqlalchemy import delete, func, select

from app.ai.errors import AIRateLimitError
from app.ai.providers.base import TranslationProvider
from app.ai.types import (
    BatchTranslationRequest,
    BatchTranslationResult,
    BatchTranslationResultItem,
    TranslationRequest,
    TranslationResult,
)
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.document import Block, BlockType, Section
from app.models.glossary import GlossaryScope, GlossaryTerm
from app.models.paper import Paper
from app.models.translation import Translation, TranslationStatus, TranslationVersion
from app.models.user import User
from app.services.translation_batches import build_translation_batches
from app.services.translations import TranslationRunInterrupted, translate_owned_paper
from tests.conftest import ApiClient
from tests.helpers import (
    academic_pdf_bytes,
    auth_headers,
    login_user,
    register_user,
    upload_pdf_bytes,
)


@dataclass
class CapturingBatchProvider(TranslationProvider):
    mode: str = "normal"
    fail_after: int | None = None
    calls: int = 0
    requests: list[BatchTranslationRequest] = field(default_factory=list)

    name = "capturing-batch"
    model = "capturing-batch-v1"

    def translate(self, request: TranslationRequest) -> TranslationResult:
        self.calls += 1
        return TranslationResult(
            translated_text=f"[single] {request.current_text}",
            provider=self.name,
            model=self.model,
        )

    def translate_batch(
        self, request: BatchTranslationRequest
    ) -> BatchTranslationResult:
        self.calls += 1
        self.requests.append(request)
        if self.fail_after is not None and self.calls > self.fail_after:
            raise AIRateLimitError(retry_after_seconds=60)

        items = [
            BatchTranslationResultItem(
                block_id=item.block_id,
                translated_text=f"[batch] {item.protected_text}",
            )
            for item in request.items
        ]
        if self.mode == "reverse":
            items.reverse()
        elif self.mode == "rotate" and len(items) > 1:
            items = items[1:] + items[:1]
        elif self.mode == "missing" and items:
            items.pop()
        elif self.mode == "duplicate" and items:
            items.append(items[0])
        elif self.mode == "unknown":
            items.append(
                BatchTranslationResultItem(
                    block_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                    translated_text="unknown",
                )
            )
        elif self.mode == "corrupt_third" and len(items) >= 3:
            items[2] = BatchTranslationResultItem(
                block_id=items[2].block_id,
                translated_text=items[2].translated_text.replace(
                    "__PAPERGPT_", "__CORRUPTED_", 1
                ),
            )
        return BatchTranslationResult(
            items=tuple(items),
            provider=self.name,
            model=self.model,
        )


def unit_block(
    order: int,
    text: str,
    section_id: uuid.UUID | None = None,
) -> Block:
    return Block(
        id=uuid.uuid4(),
        paper_id=uuid.uuid4(),
        section_id=section_id,
        page_number=1,
        block_type=BlockType.PARAGRAPH,
        original_text=text,
        reading_order=order,
        bbox={"x0": 0, "y0": 0, "x1": 1, "y1": 1},
        column_index=0,
        block_metadata={},
        is_translatable=True,
        is_stale=False,
    )


def create_paper_with_blocks(
    client: ApiClient,
    *,
    email: str,
    texts: list[str],
    section_indexes: list[int | None] | None = None,
    block_types: list[BlockType] | None = None,
    stale_indexes: set[int] | None = None,
    non_translatable_indexes: set[int] | None = None,
) -> tuple[str, dict, list[uuid.UUID]]:
    register_user(client, email)
    token = login_user(client, email)
    paper_data = upload_pdf_bytes(client, token, academic_pdf_bytes(), "batch.pdf")
    section_indexes = section_indexes or [0] * len(texts)
    block_types = block_types or [BlockType.PARAGRAPH] * len(texts)
    stale_indexes = stale_indexes or set()
    non_translatable_indexes = non_translatable_indexes or set()

    with SessionLocal() as db:
        paper = db.get(Paper, paper_data["id"])
        assert paper is not None
        paper.parse_status = "COMPLETED"
        paper.source_language = "en"
        paper.title = "Batch translation fixture"
        sections: dict[int, Section] = {}
        for section_index in sorted(
            {index for index in section_indexes if index is not None}
        ):
            section = Section(
                paper_id=paper.id,
                title_original=f"Section {section_index}",
                level=1,
                order_index=section_index,
                start_page=1,
                end_page=1,
            )
            db.add(section)
            db.flush()
            sections[section_index] = section

        blocks: list[Block] = []
        for index, text in enumerate(texts):
            section_index = section_indexes[index]
            block = Block(
                paper_id=paper.id,
                section_id=(
                    sections[section_index].id if section_index is not None else None
                ),
                page_number=1,
                block_type=block_types[index],
                original_text=text,
                reading_order=index,
                bbox={"x0": 0, "y0": 0, "x1": 1, "y1": 1},
                column_index=0,
                block_metadata={},
                is_translatable=index not in non_translatable_indexes,
                is_stale=index in stale_indexes,
            )
            db.add(block)
            blocks.append(block)
        db.commit()
        block_ids = [block.id for block in blocks]
    return token, paper_data, block_ids


def owned_user_and_paper(email: str, paper_id: str) -> tuple[User, Paper]:
    with SessionLocal() as db:
        user_id = db.scalar(select(User.id).where(User.email == email))
    assert user_id is not None
    db = SessionLocal()
    user = db.get(User, user_id)
    paper = db.get(Paper, paper_id)
    assert user is not None and paper is not None
    db.close()
    return user, paper


def run_translation(
    *,
    email: str,
    paper_id: str,
    provider: TranslationProvider,
):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        return translate_owned_paper(
            db,
            user,
            uuid.UUID(paper_id),
            "zh-CN",
            provider=provider,
        )


def test_batch_builder_limits_oversized_sections_and_stable_order() -> None:
    section_a = uuid.uuid4()
    section_b = uuid.uuid4()
    blocks = [unit_block(index, "x" * 10, section_a) for index in range(8)]
    blocks.extend(unit_block(index + 8, "y" * 10, section_b) for index in range(2))
    batches = build_translation_batches(blocks, max_blocks=6, max_chars=1_000)
    assert [len(batch.blocks) for batch in batches] == [6, 2, 2]
    assert batches[1].section_id == section_a
    assert batches[2].section_id == section_b
    assert [block.reading_order for batch in batches for block in batch.blocks] == list(
        range(10)
    )

    char_batches = build_translation_batches(
        [unit_block(0, "a" * 7), unit_block(1, "b" * 7)],
        max_blocks=6,
        max_chars=10,
    )
    assert [len(batch.blocks) for batch in char_batches] == [1, 1]

    oversized = build_translation_batches(
        [unit_block(0, "z" * 20), unit_block(1, "small")],
        max_blocks=6,
        max_chars=10,
    )
    assert [batch.character_count for batch in oversized] == [20, 5]
    assert oversized[0].blocks[0].original_text == "z" * 20


@pytest.mark.parametrize("mode", ["normal", "reverse", "rotate"])
def test_batch_mapping_uses_stable_uuid_not_output_order(
    client: ApiClient,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    email = f"batch-map-{mode}@phase1.papergpt.dev"
    _, paper, block_ids = create_paper_with_blocks(
        client,
        email=email,
        texts=["Alpha", "Beta", "Gamma"],
    )
    monkeypatch.setattr(settings, "translation_batch_max_blocks", 6)
    result = run_translation(
        email=email,
        paper_id=paper["id"],
        provider=CapturingBatchProvider(mode=mode),
    )
    assert result is not None and result.translated_count == 3
    with SessionLocal() as db:
        saved = list(
            db.scalars(
                select(Translation).where(Translation.paper_id == paper["id"])
            )
        )
    assert {translation.block_id for translation in saved} == set(block_ids)
    assert {
        translation.block_id: translation.translated_text for translation in saved
    } == {
        block_ids[0]: "[batch] Alpha",
        block_ids[1]: "[batch] Beta",
        block_ids[2]: "[batch] Gamma",
    }


@pytest.mark.parametrize("mode", ["duplicate", "unknown"])
def test_mapping_violation_stops_without_processing_rows(
    client: ApiClient,
    mode: str,
) -> None:
    email = f"batch-invalid-{mode}@phase1.papergpt.dev"
    _, paper, _ = create_paper_with_blocks(
        client,
        email=email,
        texts=["Alpha", "Beta", "Gamma"],
    )
    with pytest.raises(TranslationRunInterrupted) as captured:
        run_translation(
            email=email,
            paper_id=paper["id"],
            provider=CapturingBatchProvider(mode=mode),
        )
    assert captured.value.error.code == "AI_INVALID_BATCH_RESPONSE"
    assert captured.value.result.provider_request_count == 1
    with SessionLocal() as db:
        statuses = list(
            db.scalars(
                select(Translation.status).where(Translation.paper_id == paper["id"])
            )
        )
    assert statuses and set(statuses) == {TranslationStatus.FAILED}


def test_missing_item_fails_only_missing_translation(client: ApiClient) -> None:
    email = "batch-missing@phase1.papergpt.dev"
    _, paper, _ = create_paper_with_blocks(
        client,
        email=email,
        texts=["Alpha", "Beta", "Gamma"],
    )
    result = run_translation(
        email=email,
        paper_id=paper["id"],
        provider=CapturingBatchProvider(mode="missing"),
    )
    assert result is not None
    assert result.translated_count == 2
    assert result.failed_count == 1
    with SessionLocal() as db:
        statuses = list(
            db.scalars(
                select(Translation.status).where(Translation.paper_id == paper["id"])
            )
        )
    assert statuses.count(TranslationStatus.COMPLETED) == 2
    assert statuses.count(TranslationStatus.FAILED) == 1


def test_protected_tokens_are_isolated_and_one_corruption_is_item_local(
    client: ApiClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = "batch-protected@phase1.papergpt.dev"
    texts = [
        "O3 remained O3.",
        "O3 increased twice: O3 and O3.",
        "Citations [1–3] were retained.",
        "Exposure was 35 µg m−3 in Figure 2.",
        "Statistics were p < 0.05.",
    ]
    _, paper, block_ids = create_paper_with_blocks(
        client,
        email=email,
        texts=texts,
    )
    monkeypatch.setattr(settings, "translation_batch_max_blocks", 4)
    provider = CapturingBatchProvider(mode="corrupt_third")
    result = run_translation(
        email=email,
        paper_id=paper["id"],
        provider=provider,
    )
    assert result is not None
    assert result.translated_count == 4
    assert result.failed_count == 1
    assert result.provider_request_count == 2
    first_placeholders = [
        item.protected_text for item in provider.requests[0].items[:2]
    ]
    assert first_placeholders[0] != first_placeholders[1]
    with SessionLocal() as db:
        saved = {
            item.block_id: item
            for item in db.scalars(
                select(Translation).where(Translation.paper_id == paper["id"])
            )
        }
    assert saved[block_ids[2]].status == TranslationStatus.FAILED
    assert saved[block_ids[0]].status == TranslationStatus.COMPLETED
    assert saved[block_ids[1]].translated_text.count("O3") == 3
    assert saved[block_ids[3]].status == TranslationStatus.COMPLETED
    assert saved[block_ids[4]].status == TranslationStatus.COMPLETED


def test_batch_glossary_is_relevant_deduplicated_and_paper_overrides_global(
    client: ApiClient,
) -> None:
    email = "batch-glossary@phase1.papergpt.dev"
    _, paper, _ = create_paper_with_blocks(
        client,
        email=email,
        texts=[
            "The planetary boundary layer controls transport.",
            "Boundary effects differ from the boundary layer height.",
            "This block has no configured term.",
        ],
    )
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        db.add_all(
            [
                GlossaryTerm(
                    user_id=user.id,
                    paper_id=None,
                    source_term="planetary boundary layer",
                    target_term="global-value",
                    source_language="en",
                    target_language="zh-CN",
                    scope=GlossaryScope.USER_GLOBAL.value,
                    case_sensitive=False,
                    enabled=True,
                ),
                GlossaryTerm(
                    user_id=user.id,
                    paper_id=uuid.UUID(paper["id"]),
                    source_term="planetary boundary layer",
                    target_term="行星边界层",
                    source_language="en",
                    target_language="zh-CN",
                    scope=GlossaryScope.PAPER.value,
                    case_sensitive=False,
                    enabled=True,
                ),
                GlossaryTerm(
                    user_id=user.id,
                    paper_id=uuid.UUID(paper["id"]),
                    source_term="boundary layer height",
                    target_term="边界层高度",
                    source_language="en",
                    target_language="zh-CN",
                    scope=GlossaryScope.PAPER.value,
                    case_sensitive=False,
                    enabled=True,
                ),
                GlossaryTerm(
                    user_id=user.id,
                    paper_id=uuid.UUID(paper["id"]),
                    source_term="never present",
                    target_term="不应发送",
                    source_language="en",
                    target_language="zh-CN",
                    scope=GlossaryScope.PAPER.value,
                    case_sensitive=False,
                    enabled=True,
                ),
                GlossaryTerm(
                    user_id=user.id,
                    paper_id=uuid.UUID(paper["id"]),
                    source_term="transport",
                    target_term="disabled",
                    source_language="en",
                    target_language="zh-CN",
                    scope=GlossaryScope.PAPER.value,
                    case_sensitive=False,
                    enabled=False,
                ),
            ]
        )
        db.commit()
    provider = CapturingBatchProvider()
    result = run_translation(
        email=email,
        paper_id=paper["id"],
        provider=provider,
    )
    assert result is not None and len(provider.requests) == 1
    request = provider.requests[0]
    assert request.glossary == {
        "planetary boundary layer": "行星边界层",
        "boundary layer height": "边界层高度",
    }
    assert request.items[0].relevant_glossary == {
        "planetary boundary layer": "行星边界层"
    }
    assert request.items[1].relevant_glossary == {
        "boundary layer height": "边界层高度"
    }
    assert request.items[2].relevant_glossary == {}
    assert request.items[0].source_text.startswith("The planetary")


def test_request_reduction_25_blocks_to_5_requests_and_completed_skip(
    client: ApiClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = "batch-reduction@phase1.papergpt.dev"
    _, paper, _ = create_paper_with_blocks(
        client,
        email=email,
        texts=[f"Paragraph {index} contains stable academic text." for index in range(25)],
    )
    monkeypatch.setattr(settings, "translation_batch_max_blocks", 5)
    monkeypatch.setattr(settings, "translation_batch_max_chars", 100_000)
    provider = CapturingBatchProvider()
    result = run_translation(
        email=email,
        paper_id=paper["id"],
        provider=provider,
    )
    assert result is not None
    assert result.translated_count == 25
    assert result.batch_count == 5
    assert result.provider_request_count == 5
    assert provider.calls == 5
    assert result.provider_request_count < result.translated_count

    second_provider = CapturingBatchProvider()
    second = run_translation(
        email=email,
        paper_id=paper["id"],
        provider=second_provider,
    )
    assert second is not None
    assert second.translated_count == 0
    assert second.skipped_count == 25
    assert second.provider_request_count == 0
    assert second_provider.calls == 0


def test_eligibility_filters_stale_nontranslatable_type_completed_and_user_edit(
    client: ApiClient,
) -> None:
    email = "batch-eligibility@phase1.papergpt.dev"
    _, paper, block_ids = create_paper_with_blocks(
        client,
        email=email,
        texts=["active", "stale", "not translatable", "reference", "completed", "edited"],
        block_types=[
            BlockType.PARAGRAPH,
            BlockType.PARAGRAPH,
            BlockType.PARAGRAPH,
            BlockType.REFERENCE,
            BlockType.PARAGRAPH,
            BlockType.PARAGRAPH,
        ],
        stale_indexes={1},
        non_translatable_indexes={2},
    )
    with SessionLocal() as db:
        paper_row = db.get(Paper, paper["id"])
        assert paper_row is not None
        for index, user_modified in ((4, False), (5, True)):
            translation = Translation(
                paper_id=paper_row.id,
                block_id=block_ids[index],
                source_language="en",
                target_language="zh-CN",
                original_text=["completed", "edited"][index - 4],
                translated_text="existing",
                provider="mock",
                model="mock",
                status=TranslationStatus.COMPLETED,
                user_modified=user_modified,
                qa_status="PASSED",
            )
            db.add(translation)
        db.commit()
    provider = CapturingBatchProvider()
    result = run_translation(
        email=email,
        paper_id=paper["id"],
        provider=provider,
    )
    assert result is not None
    assert result.translated_count == 1
    assert result.skipped_count == 4
    assert [item.block_id for item in provider.requests[0].items] == [block_ids[0]]


def test_provider_wide_failure_commits_first_batch_stops_future_batches(
    client: ApiClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = "batch-provider-fatal@phase1.papergpt.dev"
    _, paper, _ = create_paper_with_blocks(
        client,
        email=email,
        texts=[f"Block {index}" for index in range(20)],
    )
    monkeypatch.setattr(settings, "translation_batch_max_blocks", 5)
    monkeypatch.setattr(settings, "translation_batch_max_chars", 100_000)
    provider = CapturingBatchProvider(fail_after=1)
    with pytest.raises(TranslationRunInterrupted) as captured:
        run_translation(
            email=email,
            paper_id=paper["id"],
            provider=provider,
        )
    summary = captured.value.result
    assert provider.calls == 2
    assert summary.provider_request_count == 2
    assert summary.translated_count == 5
    assert summary.failed_count == 5
    assert summary.remaining_count == 10
    with SessionLocal() as db:
        completed = db.scalar(
            select(func.count(Translation.id)).where(
                Translation.paper_id == paper["id"],
                Translation.status == TranslationStatus.COMPLETED,
            )
        )
        failed = db.scalar(
            select(func.count(Translation.id)).where(
                Translation.paper_id == paper["id"],
                Translation.status == TranslationStatus.FAILED,
            )
        )
        processing = db.scalar(
            select(func.count(Translation.id)).where(
                Translation.paper_id == paper["id"],
                Translation.status == TranslationStatus.PROCESSING,
            )
        )
    assert (completed, failed, processing) == (5, 5, 0)


def test_batch_creates_individual_versions_and_qa(client: ApiClient) -> None:
    email = "batch-version-qa@phase1.papergpt.dev"
    _, paper, _ = create_paper_with_blocks(
        client,
        email=email,
        texts=["One", "Two", "Three"],
    )
    result = run_translation(
        email=email,
        paper_id=paper["id"],
        provider=CapturingBatchProvider(),
    )
    assert result is not None and result.translated_count == 3
    with SessionLocal() as db:
        translations = list(
            db.scalars(
                select(Translation).where(Translation.paper_id == paper["id"])
            )
        )
        version_count = db.scalar(
            select(func.count(TranslationVersion.id)).where(
                TranslationVersion.translation_id.in_(
                    [translation.id for translation in translations]
                )
            )
        )
    assert version_count == 3
    assert all(translation.qa_status != "PENDING" for translation in translations)
