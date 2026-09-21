export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

const TOKEN_KEY = "papergpt_access_token";

export type User = {
  id: string;
  email: string;
  name: string;
  created_at: string;
};

export type Paper = {
  id: string;
  user_id: string;
  filename: string;
  original_filename: string;
  title: string | null;
  title_zh: string | null;
  file_size: number;
  file_key: string;
  file_hash: string;
  document_type: string;
  parse_status: string;
  translation_status: string;
  qa_status: string;
  source_language: string | null;
  target_language: string | null;
  page_count: number | null;
  created_at: string;
  updated_at: string;
  last_opened_at: string | null;
};

export type NormalizedBBox = {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
};

export type BlockBBox = NormalizedBBox & {
  normalized?: NormalizedBBox;
};

export type DocumentBlock = {
  id: string;
  paper_id: string;
  section_id: string | null;
  page_number: number;
  block_type: string;
  original_text: string;
  reading_order: number;
  bbox: BlockBBox;
  column_index: number | null;
  parent_block_id: string | null;
  metadata: Record<string, unknown>;
  is_translatable: boolean;
  is_stale: boolean;
  created_at: string;
  updated_at: string;
};

export type Translation = {
  id: string;
  paper_id: string;
  block_id: string;
  source_language: string;
  target_language: string;
  original_text: string;
  translated_text: string | null;
  provider: string;
  model: string;
  status: string;
  user_modified: boolean;
  qa_status: "PENDING" | "PASSED" | "WARNING" | "FAILED";
  created_at: string;
  updated_at: string;
  translated_at: string | null;
  error_message: string | null;
};

export type TranslationRun = {
  translated_count: number;
  skipped_count: number;
  failed_count: number;
};

export type BlockTranslationRun = TranslationRun & {
  translation: Translation | null;
};

export type TranslationVersion = {
  id: string;
  translation_id: string;
  translated_text: string;
  provider: string;
  model: string;
  version_number: number;
  reason: string;
  created_at: string;
};

export type TranslationQAResult = {
  id: string;
  translation_id: string;
  check_type: string;
  status: "PASSED" | "WARNING" | "FAILED";
  message: string;
  details: Record<string, unknown>;
  created_at: string;
};

export type TranslationQA = {
  translation_id: string;
  qa_status: Translation["qa_status"];
  results: TranslationQAResult[];
};

export type GlossaryScope = "USER_GLOBAL" | "PAPER";

export type GlossaryTerm = {
  id: string;
  user_id: string;
  paper_id: string | null;
  source_term: string;
  target_term: string;
  source_language: string;
  target_language: string;
  scope: GlossaryScope;
  case_sensitive: boolean;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};

export type OutlineSection = {
  id: string;
  paper_id: string;
  parent_id: string | null;
  title_original: string;
  title_zh: string | null;
  level: number;
  order_index: number;
  start_page: number;
  end_page: number;
  summary: string | null;
  created_at: string;
  children: OutlineSection[];
};

export type ParseResult = {
  paper_id: string;
  parse_status: string;
  page_count: number;
  section_count: number;
  block_count: number;
  is_scanned: boolean;
};

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export function getToken(): string | null {
  return typeof window === "undefined" ? null : localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  if (response.status === 204) return undefined as T;

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof body?.detail === "string" ? body.detail : "请求失败，请稍后重试";
    throw new ApiError(detail, response.status);
  }
  return body as T;
}
