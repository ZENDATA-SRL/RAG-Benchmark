import { parseApiError } from "@/lib/errors";

/** Single origin knob. Empty means same-origin (Vite proxy in development). */
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export function apiUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${API_BASE_URL}${path}`;
}

export function documentContentUrl(documentId: string): string {
  return apiUrl(`/api/v1/documents/${documentId}/content`);
}

export async function fetchDocumentBytes(documentId: string): Promise<ArrayBuffer> {
  const response = await fetch(documentContentUrl(documentId));
  if (!response.ok) {
    const body = await parseBody(response);
    throw parseApiError(response.status, body);
  }
  return response.arrayBuffer();
}

type Query = Record<string, string | number | boolean | undefined | null>;

function withQuery(path: string, query?: Query): string {
  if (!query) {
    return path;
  }
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const encoded = params.toString();
  return encoded ? `${path}?${encoded}` : path;
}

async function parseBody(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return null;
  }
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(apiUrl(path), { ...init, headers });
  const body = await parseBody(response);
  if (!response.ok) {
    throw parseApiError(response.status, body);
  }
  return body as T;
}

export const api = {
  get<T>(path: string, query?: Query): Promise<T> {
    return apiFetch<T>(withQuery(path, query));
  },
  post<T>(path: string, body?: unknown): Promise<T> {
    return apiFetch<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  },
  patch<T>(path: string, body: unknown): Promise<T> {
    return apiFetch<T>(path, { method: "PATCH", body: JSON.stringify(body) });
  },
  put<T>(path: string, body: unknown): Promise<T> {
    return apiFetch<T>(path, { method: "PUT", body: JSON.stringify(body) });
  },
  delete<T>(path: string): Promise<T> {
    return apiFetch<T>(path, { method: "DELETE" });
  },
};

export type UploadProgressHandler = (percent: number) => void;

export function uploadFiles(
  path: string,
  files: File[],
  onProgress?: UploadProgressHandler,
): Promise<unknown> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", apiUrl(path));
    xhr.responseType = "json";
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    xhr.onload = () => {
      const payload = xhr.response ?? null;
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(payload);
        return;
      }
      reject(parseApiError(xhr.status, payload));
    };
    xhr.onerror = () => {
      reject(parseApiError(0, { code: "network_error", message: "upload failed", details: {} }));
    };
    xhr.send(form);
  });
}
