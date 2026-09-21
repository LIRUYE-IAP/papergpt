from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.document import Block
from app.models.paper import Paper
from app.models.translation import Translation, TranslationQAResult
from app.models.user import User
from app.services.glossary import relevant_glossary

QA_PENDING = "PENDING"
QA_PASSED = "PASSED"
QA_WARNING = "WARNING"
QA_FAILED = "FAILED"


@dataclass(frozen=True)
class QACheck:
    check_type: str
    status: str
    message: str
    details: dict[str, object]


_NUMBER_PATTERN = re.compile(
    r"(?<![\w.])[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?!\w|\.\d)"
)
_UNIT_PATTERN = re.compile(
    r"(?:hPa|kPa|Pa|°\s?[CFK]|K|%|ppm|ppb|"
    r"m\s+s\s*(?:[-−⁻]\s*(?:1|¹))|"
    r"[μµu]g\s+m\s*(?:[-−⁻]\s*(?:3|³))|"
    r"mg\s+m\s*(?:[-−⁻]\s*(?:3|³)))",
    re.IGNORECASE,
)
_CITATION_PATTERN = re.compile(
    r"\[(?:\d+[a-z]?(?:\s*[-–—]\s*\d+[a-z]?)?)(?:\s*,\s*\d+[a-z]?)*\]"
    r"|\((?:[^()]*(?:19|20)\d{2}[a-z]?[^()]*)\)"
)
_FIGURE_TABLE_PATTERN = re.compile(
    r"\b(?:Figure|Fig\.|Table)\s+\d+[A-Za-z]?\b",
    re.IGNORECASE,
)
_CHEMICAL_PATTERN = re.compile(
    r"(?<!\w)(?:PM2\.5|O3|NO2|SO2|CO2)(?!\w)",
    re.IGNORECASE,
)
_STATISTICS_PATTERN = re.compile(
    r"(?<!\w)R(?:²|\^?2)(?!\w)|(?<!\w)p\s*(?:<|>|≤|≥|=)\s*0?\.\d+",
    re.IGNORECASE,
)
_PLACEHOLDER_RESIDUE = re.compile(
    r"__PAPERGPT_[A-F0-9]{16}_TOKEN_\d{4}__"
)
_UNCERTAINTY_PATTERN = re.compile(
    r"\b(?:may|might|could|suggest(?:s|ed)?|indicate(?:s|d)?|likely)\b",
    re.IGNORECASE,
)
_UNCERTAINTY_TARGET_PATTERN = re.compile(
    r"\b(?:may|might|could|suggest(?:s|ed)?|indicate(?:s|d)?|likely)\b"
    r"|可能|或许|也许|表明|显示|提示|很可能|推测",
    re.IGNORECASE,
)
_ERROR_OUTPUT_PATTERN = re.compile(
    r"(?:provider\s+error|api\s+error|rate\s+limit|traceback|exception)",
    re.IGNORECASE,
)


def _normalized_counter(pattern: re.Pattern[str], text: str) -> Counter[str]:
    return Counter(
        re.sub(r"\s+", " ", match.group(0)).strip().casefold()
        for match in pattern.finditer(text)
    )


def _consistency_check(
    check_type: str,
    label: str,
    pattern: re.Pattern[str],
    source: str,
    translated: str,
) -> QACheck:
    expected = _normalized_counter(pattern, source)
    actual = _normalized_counter(pattern, translated)
    missing = list((expected - actual).elements())
    if missing:
        return QACheck(
            check_type,
            QA_FAILED,
            f"Missing or changed {label}: {', '.join(missing)}",
            {"expected": dict(expected), "actual": dict(actual), "missing": missing},
        )
    return QACheck(
        check_type,
        QA_PASSED,
        f"{label.capitalize()} preserved",
        {"expected": dict(expected), "actual": dict(actual)},
    )


def evaluate_translation_qa(
    db: Session,
    translation: Translation,
) -> list[QACheck]:
    source = translation.original_text
    translated = (translation.translated_text or "").strip()
    checks: list[QACheck] = []

    if not translated:
        completeness = QACheck(
            "COMPLETENESS",
            QA_FAILED,
            "Translated text is empty",
            {"translated_length": 0},
        )
    elif translated == source.strip():
        completeness = QACheck(
            "COMPLETENESS",
            QA_WARNING,
            "Translated text is identical to the source",
            {"mock_provider": translation.provider == "mock"},
        )
    else:
        completeness = QACheck(
            "COMPLETENESS",
            QA_PASSED,
            "Translated text is non-empty and differs from the source",
            {
                "source_length": len(source),
                "translated_length": len(translated),
            },
        )
    checks.append(completeness)

    checks.extend(
        (
            _consistency_check(
                "NUMERIC_CONSISTENCY", "numbers", _NUMBER_PATTERN, source, translated
            ),
            _consistency_check(
                "UNIT_CONSISTENCY", "units", _UNIT_PATTERN, source, translated
            ),
            _consistency_check(
                "CITATION_CONSISTENCY",
                "citations",
                _CITATION_PATTERN,
                source,
                translated,
            ),
            _consistency_check(
                "FIGURE_TABLE_CONSISTENCY",
                "Figure/Table references",
                _FIGURE_TABLE_PATTERN,
                source,
                translated,
            ),
            _consistency_check(
                "CHEMICAL_SPECIES_CONSISTENCY",
                "chemical species",
                _CHEMICAL_PATTERN,
                source,
                translated,
            ),
            _consistency_check(
                "STATISTICS_CONSISTENCY",
                "statistical expressions",
                _STATISTICS_PATTERN,
                source,
                translated,
            ),
        )
    )

    residue = _PLACEHOLDER_RESIDUE.findall(translated)
    checks.append(
        QACheck(
            "PLACEHOLDER_INTEGRITY",
            QA_FAILED if residue else QA_PASSED,
            "Protected placeholder residue remains"
            if residue
            else "No protected placeholder residue",
            {"residue": residue},
        )
    )

    glossary = relevant_glossary(
        db,
        user_id=translation.paper.user_id,
        paper_id=translation.paper_id,
        source_language=translation.source_language,
        target_language=translation.target_language,
        texts=[source],
    )
    missing_terms = [
        {"source": source_term, "target": target_term}
        for source_term, target_term in glossary.items()
        if target_term.casefold() not in translated.casefold()
    ]
    checks.append(
        QACheck(
            "GLOSSARY_CONSISTENCY",
            QA_WARNING if missing_terms else QA_PASSED,
            "Required glossary terminology is missing"
            if missing_terms
            else "Applicable glossary terminology is present",
            {"applicable": glossary, "missing": missing_terms},
        )
    )

    uncertainty = _UNCERTAINTY_PATTERN.findall(source)
    uncertainty_preserved = not uncertainty or bool(
        _UNCERTAINTY_TARGET_PATTERN.search(translated)
    )
    checks.append(
        QACheck(
            "SCIENTIFIC_UNCERTAINTY",
            QA_PASSED if uncertainty_preserved else QA_WARNING,
            "Scientific uncertainty markers appear preserved"
            if uncertainty_preserved
            else "Source uncertainty markers may have been lost",
            {"source_markers": uncertainty},
        )
    )

    ratio = len(translated) / max(len(source), 1)
    suspicious_reasons: list[str] = []
    if translated and (ratio < 0.2 or ratio > 5.0):
        suspicious_reasons.append("extreme_length_ratio")
    if _ERROR_OUTPUT_PATTERN.search(translated):
        suspicious_reasons.append("provider_error_text")
    checks.append(
        QACheck(
            "SUSPICIOUS_OUTPUT",
            QA_WARNING if suspicious_reasons else QA_PASSED,
            "Suspicious output characteristics detected"
            if suspicious_reasons
            else "No suspicious output characteristics detected",
            {"length_ratio": round(ratio, 4), "reasons": suspicious_reasons},
        )
    )
    return checks


def aggregate_qa_status(checks: list[QACheck]) -> str:
    statuses = {check.status for check in checks}
    if QA_FAILED in statuses:
        return QA_FAILED
    if QA_WARNING in statuses:
        return QA_WARNING
    if checks:
        return QA_PASSED
    return QA_PENDING


def replace_translation_qa(
    db: Session,
    translation: Translation,
) -> list[TranslationQAResult]:
    checks = evaluate_translation_qa(db, translation)
    db.execute(
        delete(TranslationQAResult).where(
            TranslationQAResult.translation_id == translation.id
        )
    )
    results = [
        TranslationQAResult(
            translation_id=translation.id,
            check_type=check.check_type,
            status=check.status,
            message=check.message,
            details=check.details,
        )
        for check in checks
    ]
    db.add_all(results)
    translation.qa_status = aggregate_qa_status(checks)
    db.flush()
    return results


def get_owned_active_translation(
    db: Session,
    current_user: User,
    paper_id: uuid.UUID,
    translation_id: uuid.UUID,
) -> Translation | None:
    return db.scalar(
        select(Translation)
        .join(Paper, Paper.id == Translation.paper_id)
        .join(Block, Block.id == Translation.block_id)
        .where(
            Translation.id == translation_id,
            Translation.paper_id == paper_id,
            Paper.user_id == current_user.id,
            Block.is_stale.is_(False),
        )
    )


def rerun_owned_translation_qa(
    db: Session,
    current_user: User,
    paper_id: uuid.UUID,
    translation_id: uuid.UUID,
) -> Translation | None:
    translation = get_owned_active_translation(
        db, current_user, paper_id, translation_id
    )
    if translation is None:
        return None
    replace_translation_qa(db, translation)
    db.commit()
    db.refresh(translation)
    return translation
