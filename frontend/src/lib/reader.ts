import type { BlockBBox, DocumentBlock } from "@/lib/api";

export type ViewportRect = {
  left: number;
  top: number;
  width: number;
  height: number;
};

const clamp = (value: number, minimum: number, maximum: number) =>
  Math.min(Math.max(value, minimum), maximum);

export function bboxToViewport(
  bbox: BlockBBox,
  sourceWidth: number,
  sourceHeight: number,
  viewportWidth: number,
  viewportHeight: number,
): ViewportRect {
  const normalized = bbox.normalized;
  const x0 = normalized?.x0 ?? bbox.x0 / sourceWidth;
  const y0 = normalized?.y0 ?? bbox.y0 / sourceHeight;
  const x1 = normalized?.x1 ?? bbox.x1 / sourceWidth;
  const y1 = normalized?.y1 ?? bbox.y1 / sourceHeight;

  const left = clamp(x0, 0, 1) * viewportWidth;
  const top = clamp(y0, 0, 1) * viewportHeight;
  const right = clamp(x1, 0, 1) * viewportWidth;
  const bottom = clamp(y1, 0, 1) * viewportHeight;

  return {
    left,
    top,
    width: Math.max(1, right - left),
    height: Math.max(1, bottom - top),
  };
}

export function sortByReadingOrder(blocks: DocumentBlock[]): DocumentBlock[] {
  return [...blocks].sort(
    (left, right) =>
      left.reading_order - right.reading_order ||
      left.page_number - right.page_number,
  );
}

export function pageDimensions(block: DocumentBlock): {
  width: number;
  height: number;
} {
  const width = Number(block.metadata.page_width);
  const height = Number(block.metadata.page_height);
  return {
    width: Number.isFinite(width) && width > 0 ? width : 1,
    height: Number.isFinite(height) && height > 0 ? height : 1,
  };
}

export function scrollElementToCenter(
  container: HTMLElement,
  element: HTMLElement,
  behavior: ScrollBehavior = "smooth",
): void {
  const containerRect = container.getBoundingClientRect();
  const elementRect = element.getBoundingClientRect();
  const top =
    container.scrollTop +
    elementRect.top -
    containerRect.top -
    container.clientHeight / 2 +
    elementRect.height / 2;
  if (behavior === "auto") {
    const previousScrollBehavior = container.style.scrollBehavior;
    container.style.scrollBehavior = "auto";
    container.scrollTo({ top: Math.max(0, top), behavior });
    window.requestAnimationFrame(() => {
      container.style.scrollBehavior = previousScrollBehavior;
    });
    return;
  }
  container.scrollTo({ top: Math.max(0, top), behavior });
}

export function closestBlockToViewportCenter(
  container: HTMLElement,
  selector: string,
): string | null {
  const containerRect = container.getBoundingClientRect();
  const center = containerRect.top + containerRect.height / 2;
  let closestId: string | null = null;
  let closestDistance = Number.POSITIVE_INFINITY;

  container.querySelectorAll<HTMLElement>(selector).forEach((element) => {
    const rect = element.getBoundingClientRect();
    if (rect.bottom < containerRect.top || rect.top > containerRect.bottom) return;
    const distance = Math.abs((rect.top + rect.bottom) / 2 - center);
    const id = element.dataset.blockId;
    if (id && distance < closestDistance) {
      closestId = id;
      closestDistance = distance;
    }
  });

  return closestId;
}
