from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf

from app.models.document import BlockType

PARSER_VERSION = "1.1.0"
HEADING_PATTERN = re.compile(r"^(\d+(?:\.\d+){0,2})[.)]?\s+\S+")
FIGURE_CAPTION_PATTERN = re.compile(r"^(?:figure|fig\.)\s*\d+", re.IGNORECASE)
TABLE_CAPTION_PATTERN = re.compile(r"^table\s*\d+", re.IGNORECASE)
PAGE_NUMBER_PATTERN = re.compile(r"^(?:page\s+)?\d+(?:\s+of\s+\d+)?$", re.IGNORECASE)
REFERENCE_HEADING_PATTERN = re.compile(r"^(?:\d+[.)]?\s+)?references?$", re.IGNORECASE)
COMMON_HEADING_PATTERN = re.compile(
    r"^(?:abstract|introduction|background|related work|methods?|materials? and methods?|"
    r"results?|discussion|conclusions?|acknowledg(?:e)?ments?|references?)$",
    re.IGNORECASE,
)
NON_TRANSLATABLE_TYPES = {
    BlockType.FIGURE,
    BlockType.TABLE,
    BlockType.EQUATION,
    BlockType.REFERENCE,
    BlockType.HEADER,
    BlockType.FOOTER,
    BlockType.PAGE_NUMBER,
}
STRUCTURAL_FULL_WIDTH_TYPES = {
    BlockType.TITLE,
    BlockType.AUTHOR,
    BlockType.AFFILIATION,
    BlockType.ABSTRACT,
    BlockType.KEYWORDS,
}
HEADING_TYPES = {
    BlockType.HEADING_1,
    BlockType.HEADING_2,
    BlockType.HEADING_3,
}


class DocumentEngineError(RuntimeError):
    pass


@dataclass
class ParsedBlock:
    page_number: int
    page_width: float
    page_height: float
    bbox_values: tuple[float, float, float, float]
    original_text: str
    font_size: float
    font_names: list[str]
    is_bold: bool
    line_count: int
    source_block_number: int
    block_type: BlockType = BlockType.PARAGRAPH
    column_index: int | None = None
    reading_order: int = -1
    section_index: int | None = None
    is_translatable: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def x0(self) -> float:
        return self.bbox_values[0]

    @property
    def y0(self) -> float:
        return self.bbox_values[1]

    @property
    def x1(self) -> float:
        return self.bbox_values[2]

    @property
    def y1(self) -> float:
        return self.bbox_values[3]

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2

    def bbox(self) -> dict[str, Any]:
        width = max(self.page_width, 1.0)
        height = max(self.page_height, 1.0)
        return {
            "x0": round(self.x0, 3),
            "y0": round(self.y0, 3),
            "x1": round(self.x1, 3),
            "y1": round(self.y1, 3),
            "normalized": {
                "x0": round(self.x0 / width, 6),
                "y0": round(self.y0 / height, 6),
                "x1": round(self.x1 / width, 6),
                "y1": round(self.y1 / height, 6),
            },
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "page_number": self.page_number,
            "block_type": self.block_type.value,
            "original_text": self.original_text,
            "reading_order": self.reading_order,
            "bbox": self.bbox(),
            "column_index": self.column_index,
            "section_index": self.section_index,
            "is_translatable": self.is_translatable,
            "metadata": self.metadata,
        }


@dataclass
class ParsedSection:
    title_original: str
    level: int
    order_index: int
    start_page: int
    end_page: int
    heading_reading_order: int
    parent_index: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "title_original": self.title_original,
            "title_zh": None,
            "level": self.level,
            "order_index": self.order_index,
            "start_page": self.start_page,
            "end_page": self.end_page,
            "parent_index": self.parent_index,
        }


@dataclass
class ParsedDocument:
    metadata: dict[str, Any]
    pages: list[dict[str, Any]]
    sections: list[ParsedSection]
    blocks: list[ParsedBlock]
    raw_pdf_blocks: dict[str, Any]

    def layout_json(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata,
            "pages": self.pages,
            "blocks": [block.as_dict() for block in self.blocks],
        }

    def document_json(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata,
            "pages": self.pages,
            "sections": [section.as_dict() for section in self.sections],
            "blocks": [block.as_dict() for block in self.blocks],
        }


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _join_lines(lines: list[str]) -> str:
    result = ""
    for line in (_clean_text(line) for line in lines):
        if not line:
            continue
        if not result:
            result = line
            continue
        previous_word = result.rsplit(" ", 1)[-1]
        if (
            result.endswith("-")
            and len(previous_word) >= 4
            and line[0].islower()
            and previous_word.lower() not in {"well-", "self-", "state-"}
        ):
            result = result[:-1] + line
        else:
            result += " " + line
    return result


def _repetition_key(text: str) -> str:
    return re.sub(r"\d+", "#", _clean_text(text).lower())[:200]


class PDFDocumentEngine:
    def parse(self, pdf_path: Path) -> ParsedDocument:
        try:
            document = pymupdf.open(pdf_path)
        except Exception as exc:
            raise DocumentEngineError("Unable to open the PDF") from exc

        try:
            if document.needs_pass:
                raise DocumentEngineError("Password-protected PDFs are not supported")
            if document.page_count == 0:
                raise DocumentEngineError("The PDF does not contain any pages")

            raw_pages: list[dict[str, Any]] = []
            pages: list[dict[str, Any]] = []
            blocks: list[ParsedBlock] = []
            image_count = 0
            for page_index, page in enumerate(document):
                page_number = page_index + 1
                raw = page.get_text("dict", sort=False)
                page_width = float(raw.get("width", page.rect.width))
                page_height = float(raw.get("height", page.rect.height))
                blocks.extend(
                    self._extract_page_blocks(
                        raw,
                        page_number=page_number,
                        page_width=page_width,
                        page_height=page_height,
                    )
                )
                raw_blocks: list[dict[str, Any]] = []
                for raw_block in raw.get("blocks", []):
                    if int(raw_block.get("type", 0)) == 1:
                        image_count += 1
                    raw_blocks.append(self._serializable_raw_block(raw_block))
                page_record = {
                    "page_number": page_number,
                    "width": round(page_width, 3),
                    "height": round(page_height, 3),
                    "rotation": int(page.rotation),
                    "crop_box": [round(float(value), 3) for value in page.cropbox],
                    "coordinate_system": "PyMuPDF text-dict coordinates",
                }
                pages.append(page_record)
                raw_pages.append({**page_record, "blocks": raw_blocks})

            text_character_count = sum(
                len(re.sub(r"\s+", "", block.original_text))
                for block in blocks
                if block.original_text
            )
            is_scanned = image_count > 0 and text_character_count < document.page_count * 40
            body_font_size = self._body_font_size(blocks)
            self._mark_repeated_marginalia(blocks, document.page_count)
            self._classify_blocks(blocks, body_font_size)
            self._assign_columns(blocks)
            blocks = self._reconstruct_paragraphs(blocks)
            ordered_blocks = self._assign_reading_order(blocks, document.page_count)
            self._mark_references(ordered_blocks)
            sections = self._build_sections(ordered_blocks, document.page_count)
            title = next(
                (
                    block.original_text
                    for block in ordered_blocks
                    if block.block_type == BlockType.TITLE
                ),
                None,
            )
            metadata = {
                "page_count": document.page_count,
                "title": title,
                "is_scanned": is_scanned,
                "text_character_count": text_character_count,
                "image_count": image_count,
                "parser": "PyMuPDF",
                "parser_version": PARSER_VERSION,
            }
            return ParsedDocument(
                metadata=metadata,
                pages=pages,
                sections=sections,
                blocks=ordered_blocks,
                raw_pdf_blocks={"metadata": metadata, "pages": raw_pages},
            )
        except DocumentEngineError:
            raise
        except Exception as exc:
            raise DocumentEngineError("PDF layout extraction failed") from exc
        finally:
            document.close()

    def _extract_page_blocks(
        self,
        raw: dict[str, Any],
        *,
        page_number: int,
        page_width: float,
        page_height: float,
    ) -> list[ParsedBlock]:
        extracted: list[ParsedBlock] = []
        for block_number, raw_block in enumerate(raw.get("blocks", [])):
            raw_type = int(raw_block.get("type", 0))
            bbox = self._normalized_bbox(
                raw_block.get("bbox", (0, 0, 0, 0)), page_width, page_height
            )
            if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                continue
            if raw_type == 1:
                extracted.append(
                    ParsedBlock(
                        page_number=page_number,
                        page_width=page_width,
                        page_height=page_height,
                        bbox_values=bbox,
                        original_text="[Embedded figure]",
                        font_size=0.0,
                        font_names=[],
                        is_bold=False,
                        line_count=0,
                        source_block_number=block_number,
                        block_type=BlockType.FIGURE,
                        is_translatable=False,
                        metadata={
                            "source_type": "image",
                            "width": raw_block.get("width"),
                            "height": raw_block.get("height"),
                            "page_width": round(page_width, 3),
                            "page_height": round(page_height, 3),
                        },
                    )
                )
                continue
            if raw_type != 0:
                continue

            line_texts: list[str] = []
            font_sizes: list[float] = []
            font_names: set[str] = set()
            bold = False
            for line in raw_block.get("lines", []):
                spans = line.get("spans", [])
                line_texts.append("".join(str(span.get("text", "")) for span in spans))
                for span in spans:
                    text_length = max(len(str(span.get("text", ""))), 1)
                    font_sizes.extend([float(span.get("size", 0.0))] * text_length)
                    if span.get("font"):
                        font_names.add(str(span["font"]))
                    bold = bold or bool(int(span.get("flags", 0)) & 16)
            text_value = _join_lines(line_texts)
            if not text_value:
                continue
            font_size = statistics.median(font_sizes) if font_sizes else 0.0
            extracted.append(
                ParsedBlock(
                    page_number=page_number,
                    page_width=page_width,
                    page_height=page_height,
                    bbox_values=bbox,
                    original_text=text_value,
                    font_size=font_size,
                    font_names=sorted(font_names),
                    is_bold=bold,
                    line_count=len([line for line in line_texts if _clean_text(line)]),
                    source_block_number=block_number,
                    metadata={
                        "source_type": "text",
                        "font_size": round(font_size, 3),
                        "font_names": sorted(font_names),
                        "is_bold": bold,
                        "line_count": len(line_texts),
                        "source_block_number": block_number,
                        "page_width": round(page_width, 3),
                        "page_height": round(page_height, 3),
                    },
                )
            )
        return extracted

    @staticmethod
    def _normalized_bbox(
        bbox: Any, page_width: float, page_height: float
    ) -> tuple[float, float, float, float]:
        values = list(bbox)[:4]
        if len(values) != 4:
            values = [0.0, 0.0, 0.0, 0.0]
        x0, y0, x1, y1 = (float(value) for value in values)
        x0 = min(max(0.0, x0), page_width)
        x1 = min(max(0.0, x1), page_width)
        y0 = min(max(0.0, y0), page_height)
        y1 = min(max(0.0, y1), page_height)
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        return x0, y0, x1, y1

    @staticmethod
    def _serializable_raw_block(raw_block: dict[str, Any]) -> dict[str, Any]:
        if int(raw_block.get("type", 0)) == 1:
            return {
                "type": 1,
                "bbox": list(raw_block.get("bbox", [])),
                "width": raw_block.get("width"),
                "height": raw_block.get("height"),
                "extension": raw_block.get("ext"),
            }
        lines: list[dict[str, Any]] = []
        for line in raw_block.get("lines", []):
            lines.append(
                {
                    "bbox": list(line.get("bbox", [])),
                    "spans": [
                        {
                            "text": span.get("text", ""),
                            "bbox": list(span.get("bbox", [])),
                            "font": span.get("font"),
                            "size": span.get("size"),
                            "flags": span.get("flags"),
                        }
                        for span in line.get("spans", [])
                    ],
                }
            )
        return {
            "type": int(raw_block.get("type", 0)),
            "bbox": list(raw_block.get("bbox", [])),
            "lines": lines,
        }

    @staticmethod
    def _body_font_size(blocks: list[ParsedBlock]) -> float:
        candidates = [
            block.font_size
            for block in blocks
            if len(block.original_text) >= 60 and block.font_size > 0
        ]
        if not candidates:
            candidates = [block.font_size for block in blocks if block.font_size > 0]
        return statistics.median(candidates) if candidates else 10.0

    @staticmethod
    def _mark_repeated_marginalia(blocks: list[ParsedBlock], page_count: int) -> None:
        candidates: dict[str, set[int]] = {}
        for block in blocks:
            top = block.y0 / max(block.page_height, 1.0)
            bottom = block.y1 / max(block.page_height, 1.0)
            if top <= 0.12 or bottom >= 0.88:
                candidates.setdefault(_repetition_key(block.original_text), set()).add(
                    block.page_number
                )
        repeated = {
            key
            for key, page_numbers in candidates.items()
            if len(page_numbers) >= max(2, math.ceil(page_count * 0.6))
        }
        for block in blocks:
            top = block.y0 / max(block.page_height, 1.0)
            bottom = block.y1 / max(block.page_height, 1.0)
            text_value = block.original_text.strip()
            if PAGE_NUMBER_PATTERN.fullmatch(text_value) and (top <= 0.12 or bottom >= 0.88):
                block.block_type = BlockType.PAGE_NUMBER
            elif _repetition_key(text_value) in repeated and top <= 0.12:
                block.block_type = BlockType.HEADER
            elif _repetition_key(text_value) in repeated and bottom >= 0.88:
                block.block_type = BlockType.FOOTER
            if block.block_type in {
                BlockType.HEADER,
                BlockType.FOOTER,
                BlockType.PAGE_NUMBER,
            }:
                block.is_translatable = False

    @staticmethod
    def _classify_blocks(blocks: list[ParsedBlock], body_font_size: float) -> None:
        first_page_text = [
            block
            for block in blocks
            if block.page_number == 1
            and block.block_type == BlockType.PARAGRAPH
            and block.y0 / max(block.page_height, 1.0) < 0.45
            and len(block.original_text) <= 300
        ]
        title_candidate = max(first_page_text, key=lambda block: block.font_size, default=None)
        if title_candidate and title_candidate.font_size >= body_font_size * 1.3:
            title_candidate.block_type = BlockType.TITLE

        abstract_seen = False
        for block in sorted(blocks, key=lambda item: (item.page_number, item.y0, item.x0)):
            if block.block_type != BlockType.PARAGRAPH:
                continue
            text_value = block.original_text.strip()
            lower = text_value.lower()
            if FIGURE_CAPTION_PATTERN.match(text_value):
                block.block_type = BlockType.FIGURE_CAPTION
            elif TABLE_CAPTION_PATTERN.match(text_value):
                block.block_type = BlockType.TABLE_CAPTION
            elif lower.startswith("keywords") or lower.startswith("key words"):
                block.block_type = BlockType.KEYWORDS
            elif lower == "abstract" or lower.startswith("abstract:"):
                block.block_type = BlockType.ABSTRACT
                abstract_seen = True
            elif (heading_match := HEADING_PATTERN.match(text_value)) is not None:
                level = min(heading_match.group(1).count(".") + 1, 3)
                block.block_type = BlockType[f"HEADING_{level}"]
            elif COMMON_HEADING_PATTERN.fullmatch(text_value):
                block.block_type = BlockType.HEADING_1
            elif (
                block.is_bold
                and block.font_size >= body_font_size * 1.08
                and len(text_value) <= 160
            ):
                block.block_type = BlockType.HEADING_2
            elif (
                block.page_number == 1
                and title_candidate is not None
                and block.y0 > title_candidate.y1
                and not abstract_seen
                and len(text_value) <= 180
            ):
                if "@" in text_value or re.search(
                    r"\b(?:university|institute|department|laboratory|college)\b",
                    lower,
                ):
                    block.block_type = BlockType.AFFILIATION
                elif block.y0 / max(block.page_height, 1.0) < 0.45:
                    block.block_type = BlockType.AUTHOR
            elif (
                block.y1 / max(block.page_height, 1.0) > 0.83
                and block.font_size < body_font_size * 0.9
            ):
                block.block_type = BlockType.FOOTNOTE

            block.is_translatable = block.block_type not in NON_TRANSLATABLE_TYPES

    @staticmethod
    def _assign_columns(blocks: list[ParsedBlock]) -> None:
        by_page: dict[int, list[ParsedBlock]] = {}
        for block in blocks:
            by_page.setdefault(block.page_number, []).append(block)
        detection_excluded = {
            BlockType.HEADER,
            BlockType.FOOTER,
            BlockType.PAGE_NUMBER,
            *STRUCTURAL_FULL_WIDTH_TYPES,
            *HEADING_TYPES,
        }
        for page_blocks in by_page.values():
            if not page_blocks:
                continue
            page_width = page_blocks[0].page_width
            midpoint = page_width / 2
            body_candidates = [
                block
                for block in page_blocks
                if block.block_type not in detection_excluded
                and block.width <= page_width * 0.58
            ]
            left = [block for block in body_candidates if block.center_x < midpoint]
            right = [block for block in body_candidates if block.center_x >= midpoint]
            if not left or not right:
                continue

            content_left = min(block.x0 for block in body_candidates)
            content_right = max(block.x1 for block in body_candidates)
            content_width = max(content_right - content_left, 1.0)
            left_column_right = max(block.x1 for block in left)
            right_column_left = min(block.x0 for block in right)
            tolerance = page_width * 0.03

            assignable = [
                block
                for block in page_blocks
                if block.block_type not in {
                    BlockType.HEADER,
                    BlockType.FOOTER,
                    BlockType.PAGE_NUMBER,
                    *STRUCTURAL_FULL_WIDTH_TYPES,
                }
            ]
            for block in assignable:
                if block.block_type in HEADING_TYPES:
                    spans_content_width = (
                        block.width >= content_width * 0.72
                        and block.x0 <= content_left + tolerance
                        and block.x1 >= content_right - tolerance
                    )
                    if spans_content_width:
                        block.column_index = None
                        continue
                    block.column_index = 0 if block.center_x < midpoint else 1
                    continue
                if block.x1 <= right_column_left + tolerance:
                    block.column_index = 0
                elif block.x0 >= left_column_right - tolerance:
                    block.column_index = 1

    @staticmethod
    def _reconstruct_paragraphs(blocks: list[ParsedBlock]) -> list[ParsedBlock]:
        reconstructed: list[ParsedBlock] = []
        candidates = sorted(
            blocks,
            key=lambda block: (
                block.page_number,
                block.column_index if block.column_index is not None else -1,
                block.y0,
                block.x0,
            ),
        )
        for block in candidates:
            previous = reconstructed[-1] if reconstructed else None
            can_merge = (
                previous is not None
                and previous.block_type == block.block_type == BlockType.PARAGRAPH
                and previous.page_number == block.page_number
                and previous.column_index == block.column_index
                and -1.0 <= block.y0 - previous.y1 <= max(previous.font_size, block.font_size)
                and abs(previous.x0 - block.x0) <= max(8.0, block.page_width * 0.015)
                and abs(previous.font_size - block.font_size) <= 0.75
                and (
                    not previous.font_names
                    or not block.font_names
                    or bool(set(previous.font_names) & set(block.font_names))
                )
            )
            if not can_merge:
                reconstructed.append(block)
                continue

            previous.original_text = _join_lines(
                [previous.original_text, block.original_text]
            )
            previous.bbox_values = (
                min(previous.x0, block.x0),
                min(previous.y0, block.y0),
                max(previous.x1, block.x1),
                max(previous.y1, block.y1),
            )
            previous.line_count += block.line_count
            previous.metadata["line_count"] = previous.line_count
            source_numbers = previous.metadata.setdefault(
                "source_block_numbers", [previous.source_block_number]
            )
            source_numbers.append(block.source_block_number)
        return reconstructed

    @staticmethod
    def _assign_reading_order(
        blocks: list[ParsedBlock], page_count: int
    ) -> list[ParsedBlock]:
        ordered: list[ParsedBlock] = []
        for page_number in range(1, page_count + 1):
            page_blocks = [block for block in blocks if block.page_number == page_number]
            headers = sorted(
                [
                    block
                    for block in page_blocks
                    if block.block_type in {BlockType.HEADER, BlockType.PAGE_NUMBER}
                    and block.y0 / max(block.page_height, 1.0) <= 0.15
                ],
                key=lambda block: (block.y0, block.x0),
            )
            footers = sorted(
                [
                    block
                    for block in page_blocks
                    if block.block_type in {BlockType.FOOTER, BlockType.PAGE_NUMBER}
                    and block not in headers
                ],
                key=lambda block: (block.y0, block.x0),
            )
            body = [block for block in page_blocks if block not in headers + footers]
            full_width = sorted(
                [block for block in body if block.column_index is None],
                key=lambda block: (block.y0, block.x0),
            )
            column_blocks = [block for block in body if block.column_index is not None]
            page_order: list[ParsedBlock] = list(headers)
            lower_bound = -1.0
            for separator in full_width:
                segment = [
                    block
                    for block in column_blocks
                    if lower_bound <= block.y0 < separator.y0
                ]
                page_order.extend(
                    sorted(
                        segment,
                        key=lambda block: (
                            block.column_index if block.column_index is not None else 0,
                            block.y0,
                            block.x0,
                        ),
                    )
                )
                page_order.append(separator)
                lower_bound = max(lower_bound, separator.y1)
            page_order.extend(
                sorted(
                    [block for block in column_blocks if block.y0 >= lower_bound],
                    key=lambda block: (
                        block.column_index if block.column_index is not None else 0,
                        block.y0,
                        block.x0,
                    ),
                )
            )
            page_order.extend(
                sorted(
                    [block for block in body if block not in page_order],
                    key=lambda block: (
                        block.y0,
                        block.column_index if block.column_index is not None else -1,
                        block.x0,
                    ),
                )
            )
            page_order.extend(footers)
            for block in page_order:
                if block not in ordered:
                    block.reading_order = len(ordered)
                    ordered.append(block)
        return ordered

    @staticmethod
    def _mark_references(blocks: list[ParsedBlock]) -> None:
        in_references = False
        for block in blocks:
            if REFERENCE_HEADING_PATTERN.fullmatch(block.original_text.strip()):
                in_references = True
                if block.block_type not in {
                    BlockType.HEADER,
                    BlockType.FOOTER,
                    BlockType.PAGE_NUMBER,
                }:
                    block.block_type = BlockType.HEADING_1
                continue
            if in_references and block.block_type not in {
                BlockType.HEADER,
                BlockType.FOOTER,
                BlockType.PAGE_NUMBER,
            }:
                block.block_type = BlockType.REFERENCE
                block.is_translatable = False

    @staticmethod
    def _build_sections(
        blocks: list[ParsedBlock], page_count: int
    ) -> list[ParsedSection]:
        heading_levels = {
            BlockType.HEADING_1: 1,
            BlockType.HEADING_2: 2,
            BlockType.HEADING_3: 3,
        }
        sections: list[ParsedSection] = []
        stack: list[int] = []
        for block in blocks:
            level = heading_levels.get(block.block_type)
            if level is None:
                if stack:
                    block.section_index = stack[-1]
                continue
            while stack and sections[stack[-1]].level >= level:
                stack.pop()
            parent_index = stack[-1] if stack else None
            section_index = len(sections)
            sections.append(
                ParsedSection(
                    title_original=block.original_text,
                    level=level,
                    order_index=section_index,
                    start_page=block.page_number,
                    end_page=page_count,
                    heading_reading_order=block.reading_order,
                    parent_index=parent_index,
                )
            )
            stack.append(section_index)
            block.section_index = section_index

        for index, section in enumerate(sections):
            for later in sections[index + 1 :]:
                if later.level <= section.level:
                    section.end_page = max(section.start_page, later.start_page)
                    break
        return sections
