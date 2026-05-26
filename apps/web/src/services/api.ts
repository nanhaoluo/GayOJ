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
  cacheTtlMs?: number;
  apiCache?: boolean;
};

export interface DownloadResponse {
  blob: Blob;
  filename: string;
  contentType: string;
}

type CacheEntry = {
  data: unknown;
  expiresAt: number;
  staleUntil: number;
};

const DEFAULT_GET_CACHE_TTL_MS = 30_000;
const DEFAULT_GET_CACHE_STALE_MS = 5 * 60_000;
const getCache = new Map<string, CacheEntry>();
const inflightGets = new Map<string, Promise<unknown>>();

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
  clearApiCache();
}

export function clearApiCache(prefix = ''): void {
  for (const key of Array.from(getCache.keys())) {
    if (!prefix || key.includes(` ${prefix}`)) {
      getCache.delete(key);
    }
  }
}

function requestMethod(options: RequestOptions): string {
  return (options.method ?? 'GET').toUpperCase();
}

function requestCacheKey(path: string, token: string | null): string {
  return `${token ? `auth:${token}` : 'public'} ${path}`;
}

function invalidateApiCacheForMutation(path: string): void {
  clearApiCache(path);
  const prefixes = ['/contests', '/submissions', '/judge', '/clarifications', '/admin/judge-nodes'];
  for (const prefix of prefixes) {
    if (path.startsWith(prefix)) {
      clearApiCache(prefix);
    }
  }
}

async function parseJsonResponse(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.toLowerCase().includes('json')) {
    if (!response.ok) {
      throw new ApiError(response.status, text || response.statusText);
    }
    throw new ApiError(response.status, 'Invalid non-JSON response');
  }
  try {
    return JSON.parse(text);
  } catch {
    if (!response.ok) {
      throw new ApiError(response.status, text || response.statusText);
    }
    throw new ApiError(response.status, 'Invalid JSON response');
  }
}

function responseErrorDetail(response: Response, data: unknown): string {
  return data && typeof data === 'object' && 'detail' in data
    ? String((data as { detail?: unknown }).detail ?? response.statusText)
    : response.statusText;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = requestMethod(options);
  const headers = new Headers(options.headers);
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
  if (!headers.has('Content-Type') && options.body && !isFormData) {
    headers.set('Content-Type', 'application/json');
  }
  const token = getStoredAuthToken();
  if (options.auth !== false && token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  const shouldCache = method === 'GET' && options.apiCache !== false;
  const cacheKey = shouldCache ? requestCacheKey(path, options.auth === false ? null : token) : '';
  if (shouldCache) {
    const cached = getCache.get(cacheKey);
    const current = Date.now();
    if (cached && cached.expiresAt > current) {
      return cached.data as T;
    }
    if (cached && cached.staleUntil > current && !inflightGets.has(cacheKey)) {
      const refresh = apiRequest<T>(path, { ...options, apiCache: false }).then((data) => {
        getCache.set(cacheKey, {
          data,
          expiresAt: Date.now() + (options.cacheTtlMs ?? DEFAULT_GET_CACHE_TTL_MS),
          staleUntil: Date.now() + DEFAULT_GET_CACHE_STALE_MS,
        });
        return data;
      }).finally(() => inflightGets.delete(cacheKey));
      inflightGets.set(cacheKey, refresh);
      return cached.data as T;
    }
    const inflight = inflightGets.get(cacheKey);
    if (inflight) {
      return inflight as Promise<T>;
    }
  }

  const run = async (): Promise<T> => {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      method,
      headers,
    });
    const data = await parseJsonResponse(response);
    if (!response.ok) {
      throw new ApiError(response.status, responseErrorDetail(response, data));
    }
    if (method !== 'GET') {
      invalidateApiCacheForMutation(path);
    }
    return data as T;
  };

  if (shouldCache) {
    const request = run().then((data) => {
      getCache.set(cacheKey, {
        data,
        expiresAt: Date.now() + (options.cacheTtlMs ?? DEFAULT_GET_CACHE_TTL_MS),
        staleUntil: Date.now() + DEFAULT_GET_CACHE_STALE_MS,
      });
      return data;
    }).finally(() => inflightGets.delete(cacheKey));
    inflightGets.set(cacheKey, request);
    return request;
  }
  return run();
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

export function apiStreamUrl(path: string): string {
  const token = getStoredAuthToken();
  const separator = path.includes('?') ? '&' : '?';
  const tokenQuery = token ? `${separator}token=${encodeURIComponent(token)}` : '';
  return `${API_BASE}${path}${tokenQuery}`;
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
