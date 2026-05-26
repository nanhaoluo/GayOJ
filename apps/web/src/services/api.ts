export const API_BASE = import.meta.env?.VITE_API_BASE_URL ?? '/api/v1';
export const AUTH_TOKEN_KEY = 'gayoj_token';
const LEGACY_AUTH_TOKEN_KEYS = ['ctoj_token'];

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type RequestOptions = RequestInit & {
  auth?: boolean;
};

export interface DownloadResponse {
  blob: Blob;
  filename: string;
  contentType: string;
}

export function getStoredAuthToken(): string | null {
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  if (token) return token;
  for (const key of LEGACY_AUTH_TOKEN_KEYS) {
    const legacyToken = localStorage.getItem(key);
    if (legacyToken) {
      localStorage.setItem(AUTH_TOKEN_KEY, legacyToken);
      localStorage.removeItem(key);
      return legacyToken;
    }
  }
  return null;
}

export function setStoredAuthToken(token: string): void {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
  for (const key of LEGACY_AUTH_TOKEN_KEYS) {
    localStorage.removeItem(key);
  }
}

export function clearStoredAuthToken(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  for (const key of LEGACY_AUTH_TOKEN_KEYS) {
    localStorage.removeItem(key);
  }
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
  if (!headers.has('Content-Type') && options.body && !isFormData) {
    headers.set('Content-Type', 'application/json');
  }
  const token = getStoredAuthToken();
  if (options.auth !== false && token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new ApiError(response.status, data?.detail ?? response.statusText);
  }
  return data as T;
}

function filenameFromDisposition(disposition: string | null, fallback: string): string {
  if (!disposition) return fallback;
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (encoded) return decodeURIComponent(encoded.replace(/"/g, ''));
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1];
  return plain || fallback;
}

export async function apiDownload(path: string, options: RequestOptions = {}): Promise<DownloadResponse> {
  const headers = new Headers(options.headers);
  const token = getStoredAuthToken();
  if (options.auth !== false && token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });
  if (!response.ok) {
    const text = await response.text();
    let detail = response.statusText;
    try {
      const data = text ? JSON.parse(text) : null;
      detail = data?.detail ?? detail;
    } catch {
      detail = text || detail;
    }
    throw new ApiError(response.status, detail);
  }
  const contentType = response.headers.get('content-type') ?? 'application/octet-stream';
  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(response.headers.get('content-disposition'), 'download'),
    contentType,
  };
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '-';
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
}

export function problemTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    code: '代码题',
    blank: '填空题',
    single_choice: '单选题',
    multiple_choice: '多选题',
  };
  return labels[type] ?? type;
}
