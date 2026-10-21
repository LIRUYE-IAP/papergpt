from __future__ import annotations

from dataclasses import dataclass

from app.models.document import Block


@dataclass(frozen=True)
class TranslationBatch:
    blocks: tuple[Block, ...]

    @property
    def section_id(self):
        return self.blocks[0].section_id

    @property
    def section_title(self) -> str | None:
        section = self.blocks[0].section
        return section.title_original if section is not None else None

    @property
    def character_count(self) -> int:
        return sum(len(block.original_text) for block in self.blocks)


def build_translation_batches(
    blocks: list[Block],
    *,
    max_blocks: int,
    max_chars: int,
) -> list[TranslationBatch]:
    if max_blocks < 1 or max_chars < 1:
        raise ValueError("Batch limits must be positive")

    ordered = sorted(blocks, key=lambda block: block.reading_order)
    batches: list[TranslationBatch] = []
    current: list[Block] = []
    current_chars = 0

    def flush() -> None:
        nonlocal current, current_chars
        if current:
            batches.append(TranslationBatch(tuple(current)))
            current = []
            current_chars = 0

    for block in ordered:
        block_chars = len(block.original_text)
        section_changed = bool(current) and block.section_id != current[0].section_id
        limit_reached = bool(current) and (
            len(current) >= max_blocks or current_chars + block_chars > max_chars
        )
        if section_changed or limit_reached:
            flush()

        current.append(block)
        current_chars += block_chars
        if block_chars > max_chars:
            flush()

    flush()
    return batches
