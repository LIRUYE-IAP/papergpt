"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import PdfViewer, { type ReaderPanelHandle } from "@/components/PdfViewer";
import GlossaryPanel from "@/components/GlossaryPanel";
import StructuredReader from "@/components/StructuredReader";
import TranslationPanel from "@/components/TranslationPanel";
import {
  API_BASE_URL,
  ApiError,
  apiRequest,
  clearToken,
  type BlockTranslationRun,
  type DocumentBlock,
  getToken,
  type OutlineSection,
  type Paper,
  type ParseResult,
  type Translation,
  type TranslationQA,
  type TranslationRun,
  translationErrorMessage,
} from "@/lib/api";
import { sortByReadingOrder } from "@/lib/reader";

import styles from "./Reader.module.css";

type ReaderMode = "split" | "original" | "structured" | "chinese" | "bilingual";
type SyncSource = "pdf" | "document" | "restore";

type OutlineProps = {
  sections: OutlineSection[];
  onSelect: (section: OutlineSection) => void;
};

function Outline({ sections, onSelect }: OutlineProps) {
  return (
    <ul className={styles.outlineList}>
      {sections.map((section) => (
        <li key={section.id}>
          <button type="button" onClick={() => onSelect(section)}>
            {section.title_original}
          </button>
          {section.children.length > 0 && (
            <Outline sections={section.children} onSelect={onSelect} />
          )}
        </li>
      ))}
    </ul>
  );
}

export default function PaperDetailClient({ paperId }: { paperId: string }) {
  const router = useRouter();
  const pdfRef = useRef<ReaderPanelHandle>(null);
  const documentRef = useRef<ReaderPanelHandle>(null);
  const syncSourceRef = useRef<SyncSource | null>(null);
  const syncTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const initialAnchorAppliedRef = useRef(false);

  const [token, setToken] = useState("");
  const [paper, setPaper] = useState<Paper | null>(null);
  const [blocks, setBlocks] = useState<DocumentBlock[]>([]);
  const [outline, setOutline] = useState<OutlineSection[]>([]);
  const [translations, setTranslations] = useState<Translation[]>([]);
  const [qaByTranslation, setQaByTranslation] = useState<Map<string, TranslationQA>>(new Map());
  const [activeBlockId, setActiveBlockId] = useState<string | null>(null);
  const [mode, setMode] = useState<ReaderMode>("split");
  const [outlineOpen, setOutlineOpen] = useState(true);
  const [glossaryOpen, setGlossaryOpen] = useState(false);
  const [isParsing, setIsParsing] = useState(false);
  const [isTranslatingPaper, setIsTranslatingPaper] = useState(false);
  const [translatingBlockIds, setTranslatingBlockIds] = useState<Set<string>>(new Set());
  const [busyBlockId, setBusyBlockId] = useState<string | null>(null);
  const [blockTranslationErrors, setBlockTranslationErrors] = useState<Map<string, string>>(new Map());
  const [translationNotice, setTranslationNotice] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const handleAuthFailure = useCallback(() => {
    clearToken();
    router.replace("/login");
  }, [router]);

  const loadReaderData = useCallback(async (accessToken: string) => {
    const [loadedBlocks, loadedOutline, loadedTranslations] = await Promise.all([
      apiRequest<DocumentBlock[]>(`/papers/${paperId}/blocks`, {}, accessToken),
      apiRequest<OutlineSection[]>(`/papers/${paperId}/outline`, {}, accessToken),
      apiRequest<Translation[]>(
        `/papers/${paperId}/translations?target_language=zh-CN`,
        {},
        accessToken,
      ),
    ]);
    setBlocks(sortByReadingOrder(loadedBlocks));
    setOutline(loadedOutline);
    setTranslations(loadedTranslations);
  }, [paperId]);

  const loadPaper = useCallback(
    async (accessToken: string) => {
      const loadedPaper = await apiRequest<Paper>(
        `/papers/${paperId}`,
        {},
        accessToken,
      );
      setPaper(loadedPaper);
      if (loadedPaper.parse_status === "COMPLETED") {
        await loadReaderData(accessToken);
      } else {
        setBlocks([]);
        setOutline([]);
        setTranslations([]);
      }
      return loadedPaper;
    },
    [loadReaderData, paperId],
  );

  useEffect(() => {
    async function initializeReader() {
      const accessToken = getToken();
      if (!accessToken) {
        handleAuthFailure();
        return;
      }
      setToken(accessToken);
      try {
        await loadPaper(accessToken);
      } catch (requestError: unknown) {
        if (requestError instanceof ApiError && requestError.status === 401) {
          handleAuthFailure();
          return;
        }
        setError(
          requestError instanceof Error ? requestError.message : "Unable to load paper",
        );
      } finally {
        setIsLoading(false);
      }
    }

    void initializeReader();
  }, [handleAuthFailure, loadPaper]);

  useEffect(
    () => () => {
      if (syncTimerRef.current) clearTimeout(syncTimerRef.current);
    },
    [],
  );

  useEffect(() => {
    if (initialAnchorAppliedRef.current || blocks.length === 0) return;
    initialAnchorAppliedRef.current = true;
    const requestedBlockId = new URLSearchParams(window.location.search).get("block");
    const initialBlock =
      blocks.find((block) => block.id === requestedBlockId) ?? blocks[0];
    lockSync("restore");
    setActiveBlockId(initialBlock.id);
    window.setTimeout(() => {
      documentRef.current?.scrollToBlock(initialBlock.id, "auto");
      pdfRef.current?.scrollToBlock(initialBlock.id, "auto");
    }, 0);
  }, [blocks]);

  useEffect(() => {
    if (!activeBlockId) return;
    const url = new URL(window.location.href);
    url.searchParams.set("block", activeBlockId);
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }, [activeBlockId]);

  const blocksById = useMemo(
    () => new Map(blocks.map((block) => [block.id, block])),
    [blocks],
  );

  const translationsByBlock = useMemo(
    () => new Map(translations.map((translation) => [translation.block_id, translation])),
    [translations],
  );

  function lockSync(source: SyncSource) {
    syncSourceRef.current = source;
    if (syncTimerRef.current) clearTimeout(syncTimerRef.current);
    syncTimerRef.current = setTimeout(() => {
      syncSourceRef.current = null;
    }, 1200);
  }

  function syncFromPdf(blockId: string, userInitiated = false) {
    if (!blocksById.has(blockId)) return;
    if (!userInitiated && syncSourceRef.current !== null) return;
    lockSync("pdf");
    setActiveBlockId(blockId);
    documentRef.current?.scrollToBlock(blockId);
  }

  function syncFromDocument(blockId: string, userInitiated = false) {
    if (!blocksById.has(blockId)) return;
    if (!userInitiated && syncSourceRef.current !== null) return;
    lockSync("document");
    setActiveBlockId(blockId);
    pdfRef.current?.scrollToBlock(blockId);
  }

  function selectSection(section: OutlineSection) {
    const firstBlock =
      blocks.find((block) => block.section_id === section.id) ??
      blocks.find((block) => block.page_number === section.start_page);
    if (!firstBlock) return;
    lockSync("document");
    setActiveBlockId(firstBlock.id);
    documentRef.current?.scrollToBlock(firstBlock.id);
    pdfRef.current?.scrollToBlock(firstBlock.id);
  }

  function showRequestError(requestError: unknown, fallback: string) {
    if (requestError instanceof ApiError && requestError.status === 401) {
      handleAuthFailure();
      return;
    }
    setError(requestError instanceof Error ? requestError.message : fallback);
  }

  function selectMode(nextMode: ReaderMode) {
    setMode(nextMode);
    if (!activeBlockId) return;
    lockSync("restore");
    window.setTimeout(() => {
      documentRef.current?.scrollToBlock(activeBlockId, "auto");
      pdfRef.current?.scrollToBlock(activeBlockId, "auto");
    }, 0);
  }

  async function refreshTranslations() {
    if (!token) return;
    const loaded = await apiRequest<Translation[]>(
      `/papers/${paperId}/translations?target_language=zh-CN`,
      {},
      token,
    );
    setTranslations(loaded);
  }

  async function translatePaper() {
    if (!token) return;
    setIsTranslatingPaper(true);
    setError("");
    setTranslationNotice("");
    try {
      const result = await apiRequest<TranslationRun>(
        `/papers/${paperId}/translate`,
        { method: "POST", body: JSON.stringify({ target_language: "zh-CN" }) },
        token,
      );
      await refreshTranslations();
      setPaper((current) => current ? { ...current, translation_status: result.failed_count ? "FAILED" : "COMPLETED" } : current);
      setTranslationNotice(
        result.failed_count
          ? `翻译完成，但有 ${result.failed_count} 个段落失败；共使用 ${result.provider_request_count} 次 AI 请求。`
          : `翻译完成：${result.translated_count} 个段落，共使用 ${result.provider_request_count} 次 AI 请求。`,
      );
      if (mode === "original" || mode === "structured" || mode === "split") selectMode("chinese");
    } catch (requestError: unknown) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        handleAuthFailure();
        return;
      }
      const message = translationErrorMessage(requestError);
      const partial = requestError instanceof ApiError ? requestError.partialResult : null;
      setTranslationNotice(
        `${requestError instanceof ApiError && requestError.code === "AI_RATE_LIMITED" ? "翻译已暂停：" : ""}${message}` +
        (partial && partial.translated_count > 0
          ? ` 已保留 ${partial.translated_count} 个已完成段落；已使用 ${partial.provider_request_count} 次 AI 请求。`
          : ""),
      );
      setPaper((current) => current ? { ...current, translation_status: "FAILED" } : current);
      try {
        await refreshTranslations();
      } catch (refreshError: unknown) {
        if (refreshError instanceof ApiError && refreshError.status === 401) {
          handleAuthFailure();
        }
      }
    } finally {
      setIsTranslatingPaper(false);
    }
  }

  async function translateBlock(blockId: string) {
    if (!token) return;
    setTranslatingBlockIds((current) => new Set(current).add(blockId));
    setBlockTranslationErrors((current) => {
      const next = new Map(current);
      next.delete(blockId);
      return next;
    });
    setError("");
    try {
      const result = await apiRequest<BlockTranslationRun>(
        `/papers/${paperId}/blocks/${blockId}/translate`,
        { method: "POST", body: JSON.stringify({ target_language: "zh-CN" }) },
        token,
      );
      if (result.translation) {
        setTranslations((current) => [
          ...current.filter((translation) => translation.block_id !== blockId),
          result.translation!,
        ]);
      }
    } catch (requestError: unknown) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        handleAuthFailure();
        return;
      }
      setBlockTranslationErrors((current) =>
        new Map(current).set(blockId, translationErrorMessage(requestError)),
      );
      try {
        await refreshTranslations();
      } catch (refreshError: unknown) {
        if (refreshError instanceof ApiError && refreshError.status === 401) {
          handleAuthFailure();
        }
      }
    } finally {
      setTranslatingBlockIds((current) => {
        const next = new Set(current);
        next.delete(blockId);
        return next;
      });
    }
  }

  async function editTranslation(translation: Translation, value: string) {
    if (!token) return;
    setBusyBlockId(translation.block_id);
    setError("");
    try {
      const updated = await apiRequest<Translation>(
        `/papers/${paperId}/translations/${translation.id}`,
        { method: "PATCH", body: JSON.stringify({ translated_text: value }) },
        token,
      );
      setTranslations((current) => current.map((item) => item.id === updated.id ? updated : item));
      setQaByTranslation((current) => {
        const next = new Map(current);
        next.delete(updated.id);
        return next;
      });
    } catch (requestError: unknown) {
      showRequestError(requestError, "Unable to save translation");
      throw requestError;
    } finally {
      setBusyBlockId(null);
    }
  }

  async function loadTranslationQa(translation: Translation, rerun = false) {
    if (!token) return;
    setBusyBlockId(translation.block_id);
    setError("");
    try {
      const qa = await apiRequest<TranslationQA>(
        `/papers/${paperId}/translations/${translation.id}/qa`,
        { method: rerun ? "POST" : "GET" },
        token,
      );
      setQaByTranslation((current) => new Map(current).set(translation.id, qa));
      setTranslations((current) => current.map((item) => item.id === translation.id ? { ...item, qa_status: qa.qa_status } : item));
    } catch (requestError: unknown) {
      showRequestError(requestError, "Translation QA failed");
    } finally {
      setBusyBlockId(null);
    }
  }

  async function parsePaper() {
    if (!token) return;
    setIsParsing(true);
    setError("");
    setPaper((current) =>
      current ? { ...current, parse_status: "PROCESSING" } : current,
    );
    try {
      await apiRequest<ParseResult>(
        `/papers/${paperId}/parse`,
        { method: "POST" },
        token,
      );
      initialAnchorAppliedRef.current = false;
      await loadPaper(token);
    } catch (requestError: unknown) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        handleAuthFailure();
        return;
      }
      setPaper((current) =>
        current ? { ...current, parse_status: "FAILED" } : current,
      );
      setError(
        requestError instanceof Error ? requestError.message : "PDF parsing failed",
      );
    } finally {
      setIsParsing(false);
    }
  }

  if (isLoading) {
    return <main className="center-state">Loading paper reader…</main>;
  }

  if (!paper) {
    return (
      <main className="center-state">
        <div>
          <p className="error-message">{error || "Paper not found"}</p>
          <Link href="/library" className="text-link">
            Return to Library
          </Link>
        </div>
      </main>
    );
  }

  const parseStatus = paper.parse_status;
  const isCompleted = parseStatus === "COMPLETED";

  return (
    <main className={styles.readerShell}>
      <header className={styles.readerHeader}>
        <div className={styles.identity}>
          <Link href="/library" className="brand">
            PaperGPT
          </Link>
          <span aria-hidden="true">/</span>
          <strong title={paper.original_filename}>
            {paper.title || paper.original_filename}
          </strong>
        </div>
        <div className={styles.headerActions}>
          {isCompleted && (
            <button
              type="button"
              className={styles.outlineToggle}
              onClick={() => setOutlineOpen((open) => !open)}
            >
              {outlineOpen ? "Hide outline" : "Outline"}
            </button>
          )}
          <Link href="/library" className="secondary-button">
            Library
          </Link>
        </div>
      </header>

      {!isCompleted ? (
        <section className={styles.parseState}>
          <span className="status-badge">{parseStatus}</span>
          {parseStatus === "NOT_STARTED" && (
            <>
              <h1>This paper has not been parsed</h1>
              <p>Parse it to create stable document blocks and Reader anchors.</p>
            </>
          )}
          {parseStatus === "PROCESSING" && (
            <>
              <h1>Parsing document…</h1>
              <p>The Reader will open when page layout and blocks are ready.</p>
            </>
          )}
          {parseStatus === "FAILED" && (
            <>
              <h1>Parsing failed</h1>
              <p>{error || "The document engine could not parse this PDF."}</p>
            </>
          )}
          {parseStatus !== "PROCESSING" && (
            <button
              type="button"
              className="primary-button"
              disabled={isParsing}
              onClick={() => void parsePaper()}
            >
              {isParsing ? "Parsing…" : parseStatus === "FAILED" ? "Parse again" : "Parse PDF"}
            </button>
          )}
        </section>
      ) : (
        <>
          <nav className={styles.modeBar} aria-label="Reader mode">
            <button
              type="button"
              aria-pressed={mode === "split"}
              onClick={() => selectMode("split")}
            >
              Side by side
            </button>
            <button
              type="button"
              aria-pressed={mode === "original"}
              onClick={() => selectMode("original")}
            >
              Original
            </button>
            <button
              type="button"
              aria-pressed={mode === "structured"}
              onClick={() => selectMode("structured")}
            >
              Structured
            </button>
            <button
              type="button"
              aria-pressed={mode === "chinese"}
              onClick={() => selectMode("chinese")}
            >
              Chinese
            </button>
            <button
              type="button"
              aria-pressed={mode === "bilingual"}
              onClick={() => selectMode("bilingual")}
            >
              Bilingual
            </button>
            <button type="button" onClick={() => void translatePaper()} disabled={isTranslatingPaper}>
              {isTranslatingPaper ? "Translating…" : "Translate paper"}
            </button>
            <button type="button" onClick={() => setGlossaryOpen(true)}>Glossary</button>
            <span className={styles.syncStatus}>
              {activeBlockId ? `Anchor ${activeBlockId.slice(0, 8)}…` : "No active anchor"}
            </span>
          </nav>

          {error && <p className={styles.readerError}>{error}</p>}
          {translationNotice && (
            <p className={styles.translationNotice} role="status">
              {translationNotice}
            </p>
          )}

          <div
            className={`${styles.readerWorkspace} ${styles[`mode_${mode}`]} ${
              outlineOpen ? styles.withOutline : ""
            }`}
          >
            {outlineOpen && (
              <aside className={styles.outlinePanel} aria-label="Paper outline">
                <div className={styles.panelTitle}>
                  <strong>Outline</strong>
                  <span>{outline.length} top-level</span>
                </div>
                <div className={styles.outlineScroller}>
                  {outline.length > 0 ? (
                    <Outline sections={outline} onSelect={selectSection} />
                  ) : (
                    <p>No sections detected.</p>
                  )}
                </div>
              </aside>
            )}

            <PdfViewer
              ref={pdfRef}
              fileUrl={`${API_BASE_URL}/papers/${paperId}/file`}
              token={token}
              blocks={blocks}
              activeBlockId={activeBlockId}
              onBlockClick={(blockId) => syncFromPdf(blockId, true)}
              onVisibleBlockChange={(blockId) => syncFromPdf(blockId)}
            />
            {(mode === "split" || mode === "structured") && (
              <StructuredReader
                ref={documentRef}
                blocks={blocks}
                activeBlockId={activeBlockId}
                onBlockClick={(blockId) => syncFromDocument(blockId, true)}
                onVisibleBlockChange={(blockId) => syncFromDocument(blockId)}
              />
            )}
            {(mode === "chinese" || mode === "bilingual") && (
              <TranslationPanel
                ref={documentRef}
                mode={mode}
                blocks={blocks}
                translations={translationsByBlock}
                qaByTranslation={qaByTranslation}
                activeBlockId={activeBlockId}
                translatingBlockIds={translatingBlockIds}
                blockErrors={blockTranslationErrors}
                busyBlockId={busyBlockId}
                onBlockClick={(blockId) => syncFromDocument(blockId, true)}
                onVisibleBlockChange={(blockId) => syncFromDocument(blockId)}
                onTranslateBlock={translateBlock}
                onEdit={editTranslation}
                onLoadQa={loadTranslationQa}
              />
            )}
          </div>
          <GlossaryPanel
            paperId={paperId}
            token={token}
            open={glossaryOpen}
            onClose={() => setGlossaryOpen(false)}
            onAuthFailure={handleAuthFailure}
          />
        </>
      )}
    </main>
  );
}
