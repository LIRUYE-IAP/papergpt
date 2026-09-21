"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";

import type {
  DocumentBlock,
  Translation,
  TranslationQA,
} from "@/lib/api";
import { storedTranslationErrorMessage } from "@/lib/api";
import {
  closestBlockToViewportCenter,
  scrollElementToCenter,
} from "@/lib/reader";

import type { ReaderPanelHandle } from "./PdfViewer";
import QaBadge from "./QaBadge";
import styles from "./Reader.module.css";
import TranslationEditor from "./TranslationEditor";

export type TranslationReaderMode = "chinese" | "bilingual";

type TranslationPanelProps = {
  mode: TranslationReaderMode;
  blocks: DocumentBlock[];
  translations: Map<string, Translation>;
  qaByTranslation: Map<string, TranslationQA>;
  activeBlockId: string | null;
  translatingBlockIds: ReadonlySet<string>;
  blockErrors: ReadonlyMap<string, string>;
  busyBlockId: string | null;
  onBlockClick: (blockId: string) => void;
  onVisibleBlockChange: (blockId: string) => void;
  onTranslateBlock: (blockId: string) => Promise<void>;
  onEdit: (translation: Translation, value: string) => Promise<void>;
  onLoadQa: (translation: Translation, rerun?: boolean) => Promise<void>;
};

const peripheralTypes = new Set(["HEADER", "FOOTER", "PAGE_NUMBER"]);

const TranslationPanel = forwardRef<ReaderPanelHandle, TranslationPanelProps>(
  function TranslationPanel(
    {
      mode,
      blocks,
      translations,
      qaByTranslation,
      activeBlockId,
      translatingBlockIds,
      blockErrors,
      busyBlockId,
      onBlockClick,
      onVisibleBlockChange,
      onTranslateBlock,
      onEdit,
      onLoadQa,
    },
    ref,
  ) {
    const containerRef = useRef<HTMLDivElement>(null);
    const scrollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const [editingId, setEditingId] = useState<string | null>(null);

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
      <div className={styles.documentPanel} data-reader-mode={mode}>
        <div className={styles.panelTitle}>
          <strong>{mode === "chinese" ? "Chinese reader" : "Bilingual reader"}</strong>
          <span>{translations.size}/{blocks.filter((block) => block.is_translatable).length} translated</span>
        </div>
        <div ref={containerRef} className={styles.documentScroller} onScroll={handleScroll}>
          <article className={styles.documentPage}>
            {blocks.map((block) => {
              const translation = translations.get(block.id);
              const isBusy = busyBlockId === block.id;
              const isTranslating = translatingBlockIds.has(block.id);
              const failureMessage = blockErrors.get(block.id) ?? (
                translation?.status === "FAILED"
                  ? storedTranslationErrorMessage(translation.error_message)
                  : null
              );
              return (
                <div
                  key={block.id}
                  id={`block-${block.id}`}
                  role="button"
                  tabIndex={0}
                  className={`${styles.documentBlock} ${styles.translationBlock} ${
                    activeBlockId === block.id ? styles.documentBlockActive : ""
                  }`}
                  data-block-id={block.id}
                  data-translation-block-id={translation?.block_id ?? ""}
                  data-reader-block="true"
                  data-sync-block={peripheralTypes.has(block.block_type) ? "false" : "true"}
                  onClick={() => onBlockClick(block.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onBlockClick(block.id);
                    }
                  }}
                >
                  <span className={styles.blockMeta}>
                    {block.block_type.replaceAll("_", " ")} · page {block.page_number}
                  </span>
                  {mode === "bilingual" && (
                    <span className={styles.originalText}>{block.original_text}</span>
                  )}
                  {failureMessage ? (
                    <>
                      {translation?.translated_text && (
                        <span className={styles.previousTranslation}>
                          {translation.translated_text}
                        </span>
                      )}
                      <span
                        className={styles.translationFailure}
                        role="alert"
                        onClick={(event) => event.stopPropagation()}
                      >
                        <strong>翻译失败</strong>
                        <span>{failureMessage}</span>
                        <button
                          type="button"
                          disabled={isTranslating}
                          onClick={() => void onTranslateBlock(block.id)}
                        >
                          {isTranslating ? "Translating…" : "Retry"}
                        </button>
                      </span>
                    </>
                  ) : translation?.translated_text ? (
                    editingId === translation.id ? (
                      <TranslationEditor
                        translation={translation}
                        saving={isBusy}
                        onCancel={() => setEditingId(null)}
                        onSave={async (value) => {
                          await onEdit(translation, value);
                          setEditingId(null);
                        }}
                      />
                    ) : (
                      <>
                        <span className={styles.translatedText}>{translation.translated_text}</span>
                        <span className={styles.translationActions} onClick={(event) => event.stopPropagation()}>
                          {translation.user_modified && <span className={styles.manualBadge}>人工修改</span>}
                          <QaBadge
                            translation={translation}
                            qa={qaByTranslation.get(translation.id)}
                            loading={isBusy}
                            onLoad={() => void onLoadQa(translation)}
                            onRerun={() => void onLoadQa(translation, true)}
                          />
                          <button type="button" onClick={() => setEditingId(translation.id)}>
                            Edit translation
                          </button>
                        </span>
                      </>
                    )
                  ) : block.is_translatable ? (
                    <span className={styles.missingTranslation}>
                      <span>尚未翻译</span>
                      <button
                        type="button"
                        disabled={isTranslating}
                        onClick={(event) => {
                          event.stopPropagation();
                          void onTranslateBlock(block.id);
                        }}
                      >
                        {isTranslating ? "Translating…" : "Translate block"}
                      </button>
                    </span>
                  ) : (
                    <span className={styles.peripheralTranslation}>{block.original_text}</span>
                  )}
                </div>
              );
            })}
          </article>
        </div>
      </div>
    );
  },
);

export default TranslationPanel;
