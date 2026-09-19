"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
} from "react";

import type { DocumentBlock } from "@/lib/api";
import {
  closestBlockToViewportCenter,
  scrollElementToCenter,
} from "@/lib/reader";

import type { ReaderPanelHandle } from "./PdfViewer";
import styles from "./Reader.module.css";

type StructuredReaderProps = {
  blocks: DocumentBlock[];
  activeBlockId: string | null;
  onBlockClick: (blockId: string) => void;
  onVisibleBlockChange: (blockId: string) => void;
};

const peripheralTypes = new Set(["HEADER", "FOOTER", "PAGE_NUMBER"]);

function blockClass(blockType: string): string {
  if (blockType === "TITLE") return styles.blockTitle;
  if (blockType === "AUTHOR") return styles.blockAuthor;
  if (blockType === "AFFILIATION") return styles.blockAffiliation;
  if (blockType === "ABSTRACT") return styles.blockAbstract;
  if (blockType === "KEYWORDS") return styles.blockKeywords;
  if (blockType === "HEADING_1") return styles.blockHeadingOne;
  if (blockType === "HEADING_2") return styles.blockHeadingTwo;
  if (blockType === "HEADING_3") return styles.blockHeadingThree;
  if (blockType === "FIGURE_CAPTION" || blockType === "TABLE_CAPTION") {
    return styles.blockCaption;
  }
  if (blockType === "EQUATION") return styles.blockEquation;
  if (blockType === "FOOTNOTE") return styles.blockFootnote;
  if (blockType === "REFERENCE") return styles.blockReference;
  if (peripheralTypes.has(blockType)) return styles.blockPeripheral;
  return styles.blockParagraph;
}

const StructuredReader = forwardRef<ReaderPanelHandle, StructuredReaderProps>(
  function StructuredReader(
    { blocks, activeBlockId, onBlockClick, onVisibleBlockChange },
    ref,
  ) {
    const containerRef = useRef<HTMLDivElement>(null);
    const scrollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    useEffect(
      () => () => {
        if (scrollTimerRef.current) clearTimeout(scrollTimerRef.current);
      },
      [],
    );

    useImperativeHandle(ref, () => ({
      scrollToBlock(blockId, behavior = "smooth") {
        const container = containerRef.current;
        const element = window.document.getElementById(`block-${blockId}`);
        if (container && element) scrollElementToCenter(container, element, behavior);
      },
    }));

    function handleScroll() {
      if (scrollTimerRef.current) clearTimeout(scrollTimerRef.current);
      scrollTimerRef.current = setTimeout(() => {
        const container = containerRef.current;
        if (!container) return;
        const blockId = closestBlockToViewportCenter(
          container,
          '[data-reader-block="true"][data-sync-block="true"]',
        );
        if (blockId) onVisibleBlockChange(blockId);
      }, 140);
    }

    return (
      <div className={styles.documentPanel}>
        <div className={styles.panelTitle}>
          <strong>Structured document</strong>
          <span>{blocks.length} blocks</span>
        </div>
        <div
          ref={containerRef}
          className={styles.documentScroller}
          onScroll={handleScroll}
        >
          <article className={styles.documentPage}>
            {blocks.map((block) => (
              <button
                key={block.id}
                id={`block-${block.id}`}
                type="button"
                className={`${styles.documentBlock} ${blockClass(block.block_type)} ${
                  activeBlockId === block.id ? styles.documentBlockActive : ""
                }`}
                data-block-id={block.id}
                data-reader-block="true"
                data-sync-block={peripheralTypes.has(block.block_type) ? "false" : "true"}
                onClick={() => onBlockClick(block.id)}
              >
                <span className={styles.blockMeta}>
                  {block.block_type.replaceAll("_", " ")} · page {block.page_number}
                </span>
                <span className={styles.blockText}>{block.original_text}</span>
              </button>
            ))}
          </article>
        </div>
      </div>
    );
  },
);

export default StructuredReader;
