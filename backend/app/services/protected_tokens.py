from dataclasses import dataclass
import hashlib
import re


class TokenRestorationError(ValueError):
    pass


@dataclass(frozen=True)
class ProtectedText:
    text: str
    tokens: dict[str, str]


_PATTERNS = (
    re.compile(r"\[(?:\d+[a-z]?(?:\s*[-–—]\s*\d+[a-z]?)?)(?:\s*,\s*\d+[a-z]?)*\]"),
    re.compile(
        r"\((?:[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’-]+"
        r"(?:\s+(?:et\s+al\.|(?:and|&)\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’-]+))?"
        r"\s*,\s*(?:19|20)\d{2}[a-z]?)"
        r"(?:\s*;\s*[^()]*?(?:19|20)\d{2}[a-z]?)*\)"
    ),
    re.compile(r"\b(?:Figure|Fig\.|Table)\s+\d+[A-Za-z]?\b", re.IGNORECASE),
    re.compile(r"(?<!\w)p\s*(?:<|>|≤|≥|=)\s*0?\.\d+", re.IGNORECASE),
    re.compile(r"(?<!\w)R(?:²|\^?2)(?!\w)"),
    re.compile(r"(?<!\w)(?:PM2\.5|O3|NO2|SO2|CO2)(?!\w)", re.IGNORECASE),
    re.compile(
        r"(?<![\w.])[+-]?\d+(?:\.\d+)?\s*"
        r"(?:hPa|kPa|Pa|°\s?[CFK]|K|%|ppm|ppb|"
        r"m\s+s\s*(?:[-−⁻]\s*(?:1|¹))|"
        r"[μµu]g\s+m\s*(?:[-−⁻]\s*(?:3|³))|"
        r"mg\s+m\s*(?:[-−⁻]\s*(?:3|³)))"
        r"(?!\w)",
        re.IGNORECASE,
    ),
)

_PLACEHOLDER_PATTERN = re.compile(
    r"__PAPERGPT_([A-F0-9]{16})_TOKEN_(\d{4})__"
)


def _placeholder_namespace(source_text: str, namespace_seed: str | None = None) -> str:
    counter = 0
    while True:
        digest_source = (
            f"{counter}\0{source_text}"
            if namespace_seed is None
            else f"{counter}\0{namespace_seed}\0{source_text}"
        ).encode("utf-8")
        namespace = hashlib.sha256(digest_source).hexdigest()[:16].upper()
        collision_pattern = re.compile(
            rf"__PAPERGPT_{namespace}_TOKEN_\d{{4}}__"
        )
        if collision_pattern.search(source_text) is None:
            return namespace
        counter += 1


def protect_scientific_tokens(
    source_text: str,
    *,
    namespace_seed: str | None = None,
) -> ProtectedText:
    matches: list[tuple[int, int, str]] = []
    occupied: list[tuple[int, int]] = []
    for pattern in _PATTERNS:
        for match in pattern.finditer(source_text):
            span = match.span()
            if any(span[0] < end and span[1] > start for start, end in occupied):
                continue
            matches.append((span[0], span[1], match.group(0)))
            occupied.append(span)

    matches.sort(key=lambda item: item[0])
    tokens: dict[str, str] = {}
    parts: list[str] = []
    cursor = 0
    namespace = _placeholder_namespace(source_text, namespace_seed)
    for index, (start, end, value) in enumerate(matches):
        placeholder = f"__PAPERGPT_{namespace}_TOKEN_{index:04d}__"
        parts.append(source_text[cursor:start])
        parts.append(placeholder)
        tokens[placeholder] = value
        cursor = end
    parts.append(source_text[cursor:])
    return ProtectedText(text="".join(parts), tokens=tokens)


def restore_scientific_tokens(translated_text: str, tokens: dict[str, str]) -> str:
    restored = translated_text
    for placeholder, original in tokens.items():
        if restored.count(placeholder) != 1:
            raise TokenRestorationError(
                f"Protected token placeholder was changed: {placeholder}"
            )
        restored = restored.replace(placeholder, original)

    namespaces = {
        match.group(1)
        for placeholder in tokens
        if (match := _PLACEHOLDER_PATTERN.fullmatch(placeholder)) is not None
    }
    for namespace in namespaces:
        unknown_pattern = re.compile(
            rf"__PAPERGPT_{namespace}_TOKEN_\d{{4}}__"
        )
        if unknown_pattern.search(restored) is not None:
            raise TokenRestorationError(
                "Translation returned an unknown protected token"
            )
    return restored
