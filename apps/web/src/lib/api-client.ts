import type {
  Book,
  BookStats,
  BookSummary,
  CreateBookRequest,
  DailyNarrationHours,
  DailyUploadCount,
  FileMetadata,
  FileUploadResponse,
  UploadStats,
  Voice,
} from "@ai-audiobook-generator/shared";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const BOOK_OWNER = process.env.NEXT_PUBLIC_BOOK_OWNER || "local-dev";
const BOOK_TOKEN = process.env.NEXT_PUBLIC_BOOK_TOKEN || "dev-book-token";

/** Typed API error with HTTP status code for caller-side branching. */
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** True for 408, 429, 500, 502, 503, 504 — worth retrying. */
  get isRetryable(): boolean {
    return [408, 429, 500, 502, 503, 504].includes(this.status);
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isConflict(): boolean {
    return this.status === 409;
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  const headers = new Headers(init?.headers);
  if (path === "/books" || path.startsWith("/books/")) {
    headers.set("X-Book-Owner", BOOK_OWNER);
    headers.set("X-Book-Token", BOOK_TOKEN);
  }
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    // Network failure (offline, DNS, CORS, etc.)
    throw new ApiError("Network error — check your connection", 0);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(
      body.detail || `API error: ${res.status}`,
      res.status,
    );
  }
  return res.json();
}

export async function getHealth() {
  return apiFetch<{ status: string; b2_connected: boolean }>("/health");
}

export async function getFiles(prefix = "", limit = 100) {
  return apiFetch<FileMetadata[]>(
    `/files?prefix=${encodeURIComponent(prefix)}&limit=${limit}`
  );
}

export async function getFileStats() {
  return apiFetch<UploadStats>("/files/stats");
}

export async function getUploadActivity(days = 7) {
  return apiFetch<DailyUploadCount[]>(`/files/stats/activity?days=${days}`);
}

export async function getFile(key: string) {
  return apiFetch<FileMetadata>(`/files/${key}`);
}

export async function getDownloadUrl(key: string) {
  return apiFetch<{ url: string }>(`/files/${key}/download`);
}

/** Preview-only presigned URL — does NOT increment the download counter. */
export async function getPreviewUrl(key: string) {
  return apiFetch<{ url: string }>(`/files/${key}/preview`);
}

export async function deleteFile(key: string) {
  return apiFetch<{ deleted: boolean; key: string }>(`/files/${key}`, {
    method: "DELETE",
  });
}

// ----- Audiobook domain -----

export async function getVoices() {
  return apiFetch<Voice[]>("/voices");
}

export async function getBooks() {
  return apiFetch<BookSummary[]>("/books");
}

export async function getBook(id: string) {
  return apiFetch<Book>(`/books/${id}`);
}

export async function getBookStats() {
  return apiFetch<BookStats>("/books/stats");
}

export async function getBookActivity(days = 7) {
  return apiFetch<DailyNarrationHours[]>(`/books/stats/activity?days=${days}`);
}

export async function createBook(request: CreateBookRequest) {
  return apiFetch<Book>("/books", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

export async function deleteBook(id: string) {
  return apiFetch<{ deleted: boolean; id: string }>(`/books/${id}`, {
    method: "DELETE",
  });
}

export async function getMasterDownloadUrl(id: string) {
  return apiFetch<{ url: string }>(`/books/${id}/master/download`);
}

export async function getChapterStreamUrl(id: string, index: number) {
  return apiFetch<{ url: string }>(`/books/${id}/chapters/${index}/stream`);
}

export function uploadFile(
  file: File,
  onProgress?: (percent: number) => void
): Promise<FileUploadResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        try {
          const body = JSON.parse(xhr.responseText);
          reject(new ApiError(body.detail || `Upload failed: ${xhr.status}`, xhr.status));
        } catch {
          reject(new ApiError(`Upload failed: ${xhr.status}`, xhr.status));
        }
      }
    });

    xhr.addEventListener("error", () =>
      reject(new ApiError("Network error — check your connection", 0)),
    );
    xhr.addEventListener("abort", () =>
      reject(new ApiError("Upload aborted", 0)),
    );

    xhr.open("POST", `${API_BASE}/upload`);
    xhr.send(formData);
  });
}
