"use client";

import type { PDFDocumentProxy } from "pdfjs-dist";
import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";

import type { DocumentBlock } from "@/lib/api";
import {
  bboxToViewport,
  closestBlockToViewportCenter,
  pageDimensions,
  scrollElementToCenter,
} from "@/lib/reader";

import styles from "./Reader.module.css";

export type ReaderPanelHandle = {
  scrollToBlock: (blockId: string, behavior?: ScrollBehavior) => void;
};

type PdfViewerProps = {
  fileUrl: string;
  token: string;
  blocks: DocumentBlock[];
  activeBlockId: string | null;
  onBlockClick: (blockId: string) => void;
  onVisibleBlockChange: (blockId: string) => void;
};

type PdfPageProps = {
  document: PDFDocumentProxy;
  pageNumber: number;
  availableWidth: number;
  blocks: DocumentBlock[];
  activeBlockId: string | null;
  onBlockClick: (blockId: string) => void;
};

function PdfPage({
  document,
  pageNumber,
  availableWidth,
  blocks,
  activeBlockId,
  onBlockClick,
}: PdfPageProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [viewportSize, setViewportSize] = useState({ width: 0, height: 0 });
  const [renderError, setRenderError] = useState("");

  useEffect(() => {
    let cancelled = false;
    let renderTask: { cancel: () => void; promise: Promise<void> } | null = null;

    async function renderPage() {
      const page = await document.getPage(pageNumber);
      if (!cancelled) setRenderError("");
      const initialViewport = page.getViewport({ scale: 1 });
      const scale = Math.max(0.1, availableWidth / initialViewport.width);
      const viewport = page.getViewport({ scale });
      const canvas = canvasRef.current;
      if (!canvas || cancelled) return;

      const pixelRatio = window.devicePixelRatio || 1;
      canvas.width = Math.floor(viewport.width * pixelRatio);
      canvas.height = Math.floor(viewport.height * pixelRatio);
      canvas.style.width = `${viewport.width}px`;
      canvas.style.height = `${viewport.height}px`;
      setViewportSize({ width: viewport.width, height: viewport.height });

      const context = canvas.getContext("2d");
      if (!context) throw new Error("Canvas 2D context is unavailable");
      renderTask = page.render({
        canvas: null,
        canvasContext: context,
        viewport,
        transform: pixelRatio === 1 ? undefined : [pixelRatio, 0, 0, pixelRatio, 0, 0],
      });
      await renderTask.promise;
    }

    void renderPage().catch((error: unknown) => {
      if (cancelled || (error instanceof Error && error.name === "RenderingCancelledException")) {
        return;
      }
      setRenderError(error instanceof Error ? error.message : "PDF page render failed");
    });

    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [availableWidth, document, pageNumber]);

  return (
    <section
      className={styles.pdfPage}
      data-page-number={pageNumber}
      style={
        viewportSize.width
          ? { width: viewportSize.width, height: viewportSize.height }
          : undefined
      }
    >
      <canvas ref={canvasRef} aria-label={`PDF page ${pageNumber}`} />
      {viewportSize.width > 0 &&
        blocks.map((block) => {
          const source = pageDimensions(block);
          const rectangle = bboxToViewport(
            block.bbox,
            source.width,
            source.height,
            viewportSize.width,
            viewportSize.height,
          );
          return (
            <button
              key={block.id}
              id={`pdf-block-${block.id}`}
              type="button"
              className={`${styles.pdfOverlay} ${
                activeBlockId === block.id ? styles.pdfOverlayActive : ""
              }`}
              data-block-id={block.id}
              data-sync-block={
                ["HEADER", "FOOTER", "PAGE_NUMBER"].includes(block.block_type)
                  ? "false"
                  : "true"
              }
              aria-label={`Locate ${block.block_type} block in structured reader`}
              title={`${block.block_type}: ${block.original_text.slice(0, 100)}`}
              style={rectangle}
              onClick={() => onBlockClick(block.id)}
            />
          );
        })}
      <span className={styles.pageNumber}>{pageNumber}</span>
      {renderError && <p className={styles.pageError}>{renderError}</p>}
    </section>
  );
}

const PdfViewer = forwardRef<ReaderPanelHandle, PdfViewerProps>(function PdfViewer(
  {
    fileUrl,
    token,
    blocks,
    activeBlockId,
    onBlockClick,
    onVisibleBlockChange,
  },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const pageAreaRef = useRef<HTMLDivElement>(null);
  const scrollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const suppressScrollUntilRef = useRef(0);
  const initialAnchorRestoredRef = useRef(false);
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null);
  const [availableWidth, setAvailableWidth] = useState(720);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let active = true;
    let loadingTask: ReturnType<(typeof import("pdfjs-dist"))["getDocument"]> | null =
      null;

    async function loadPdf() {
      const pdfjs = await import("pdfjs-dist");
      pdfjs.GlobalWorkerOptions.workerSrc = new URL(
        "pdfjs-dist/build/pdf.worker.min.mjs",
        import.meta.url,
      ).toString();
      loadingTask = pdfjs.getDocument({
        url: fileUrl,
        httpHeaders: { Authorization: `Bearer ${token}` },
        withCredentials: false,
      });
      const loadedDocument = await loadingTask.promise;
      if (active) {
        setLoadError("");
        setDocument(loadedDocument);
      }
    }

    initialAnchorRestoredRef.current = false;
    void loadPdf().catch((error: unknown) => {
      if (!active) return;
      setLoadError(error instanceof Error ? error.message : "Unable to load PDF");
    });

    return () => {
      active = false;
      void loadingTask?.destroy();
    };
  }, [fileUrl, token]);

  useEffect(() => {
    if (!document || !activeBlockId || initialAnchorRestoredRef.current) return;
    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      const container = containerRef.current;
      const element = documentElement(`pdf-block-${activeBlockId}`);
      if (container && element) {
        initialAnchorRestoredRef.current = true;
        suppressScrollUntilRef.current = Date.now() + 800;
        scrollElementToCenter(container, element, "auto");
        window.clearInterval(timer);
      } else if (attempts >= 30) {
        window.clearInterval(timer);
      }
    }, 100);
    return () => window.clearInterval(timer);
  }, [activeBlockId, document]);

  useEffect(() => {
    const pageArea = pageAreaRef.current;
    if (!pageArea) return;
    const updateWidth = () => setAvailableWidth(Math.max(260, pageArea.clientWidth - 32));
    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(pageArea);
    return () => observer.disconnect();
  }, []);

  useEffect(
    () => () => {
      if (scrollTimerRef.current) clearTimeout(scrollTimerRef.current);
    },
    [],
  );

  useImperativeHandle(ref, () => ({
    scrollToBlock(blockId, behavior = "smooth") {
      const container = containerRef.current;
      const element = documentElement(`pdf-block-${blockId}`);
      if (container && element) scrollElementToCenter(container, element, behavior);
    },
  }));

  function handleScroll() {
    if (Date.now() < suppressScrollUntilRef.current) return;
    if (scrollTimerRef.current) clearTimeout(scrollTimerRef.current);
    scrollTimerRef.current = setTimeout(() => {
      const container = containerRef.current;
      if (!container) return;
      const blockId = closestBlockToViewportCenter(
        container,
        `.${styles.pdfOverlay}[data-sync-block="true"]`,
      );
      if (blockId) onVisibleBlockChange(blockId);
    }, 100);
  }

  const blocksByPage = new Map<number, DocumentBlock[]>();
  blocks.forEach((block) => {
    const pageBlocks = blocksByPage.get(block.page_number) ?? [];
    pageBlocks.push(block);
    blocksByPage.set(block.page_number, pageBlocks);
  });

  return (
    <div className={styles.pdfPanel}>
      <div className={styles.panelTitle}>
        <strong>Original PDF</strong>
        <span>{document ? `${document.numPages} pages` : "Loading…"}</span>
      </div>
      <div ref={containerRef} className={styles.pdfScroller} onScroll={handleScroll}>
        <div ref={pageAreaRef} className={styles.pdfPages}>
          {loadError && <p className={styles.panelError}>{loadError}</p>}
          {!document && !loadError && <p className={styles.panelMessage}>Loading PDF.js…</p>}
          {document &&
            Array.from({ length: document.numPages }, (_, index) => index + 1).map(
              (pageNumber) => (
                <PdfPage
                  key={pageNumber}
                  document={document}
                  pageNumber={pageNumber}
                  availableWidth={availableWidth}
                  blocks={blocksByPage.get(pageNumber) ?? []}
                  activeBlockId={activeBlockId}
                  onBlockClick={onBlockClick}
                />
              ),
            )}
        </div>
      </div>
    </div>
  );
});

function documentElement(id: string): HTMLElement | null {
  return window.document.getElementById(id);
}

export default PdfViewer;
