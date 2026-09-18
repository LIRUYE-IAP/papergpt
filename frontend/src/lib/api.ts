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
  created_at: string;
  updated_at: string;
  last_opened_at: string | null;
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
