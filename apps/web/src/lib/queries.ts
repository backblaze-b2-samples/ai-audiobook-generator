"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  createBook,
  deleteBook,
  deleteFile,
  getBook,
  getBookActivity,
  getBooks,
  getBookStats,
  getFiles,
  getFileStats,
  getPreviewUrl,
  getUploadActivity,
  getVoices,
} from "@/lib/api-client";
import type {
  Book,
  CreateBookRequest,
  FileMetadata,
} from "@ai-audiobook-generator/shared";

// Single source of truth for query keys. Keep these tightly scoped so that
// invalidating "files" doesn't blow away unrelated caches, and so an IDE
// "find usages" of `qk.files` reveals every consumer.
export const qk = {
  all: ["b2"] as const,
  files: (prefix?: string, limit?: number) =>
    [...qk.all, "files", prefix ?? "", limit ?? 100] as const,
  stats: () => [...qk.all, "stats"] as const,
  uploadActivity: (days: number) =>
    [...qk.all, "stats", "activity", days] as const,
  preview: (key: string) => [...qk.all, "preview", key] as const,
  books: () => [...qk.all, "books"] as const,
  book: (id: string) => [...qk.all, "books", id] as const,
  bookStats: () => [...qk.all, "books", "stats"] as const,
  bookActivity: (days: number) =>
    [...qk.all, "books", "activity", days] as const,
  voices: () => [...qk.all, "voices"] as const,
};

// A book is "in flight" while it is still being narrated/assembled — poll it.
function isInFlight(status: string): boolean {
  return status === "pending" || status === "rendering" || status === "assembling";
}

export function useFiles(prefix = "", limit = 100) {
  return useQuery<FileMetadata[], ApiError>({
    queryKey: qk.files(prefix, limit),
    queryFn: () => getFiles(prefix, limit),
  });
}

export function useFileStats() {
  return useQuery({
    queryKey: qk.stats(),
    queryFn: getFileStats,
  });
}

export function useUploadActivity(days = 7) {
  return useQuery({
    queryKey: qk.uploadActivity(days),
    queryFn: () => getUploadActivity(days),
  });
}

// Presigned preview URL — only fetched when `enabled` is true (e.g., when
// the dialog opens for a specific file). Kept short-lived (60s) because
// the URL itself has a presigned expiry and is cheap to regenerate.
export function usePreviewUrl(key: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: qk.preview(key ?? ""),
    queryFn: () => getPreviewUrl(key as string),
    enabled: enabled && !!key,
    staleTime: 60_000,
  });
}

export function useDeleteFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (fileKey: string) => deleteFile(fileKey),
    // After delete, blow away every cached file list + stats. Cheap and
    // correct — the dashboard re-fetches lazily as components remount.
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.all });
    },
  });
}

// ----- Audiobook hooks -----

export function useVoices() {
  return useQuery({
    queryKey: qk.voices(),
    queryFn: getVoices,
    staleTime: 5 * 60_000,
  });
}

export function useBooks() {
  return useQuery({
    queryKey: qk.books(),
    queryFn: getBooks,
    // Poll the library while any book is still being narrated so progress
    // updates without a manual refresh.
    refetchInterval: (query) => {
      const data = query.state.data as { status: string }[] | undefined;
      return data?.some((b) => isInFlight(b.status)) ? 3000 : false;
    },
  });
}

export function useBook(id: string | undefined) {
  return useQuery<Book, ApiError>({
    queryKey: qk.book(id ?? ""),
    queryFn: () => getBook(id as string),
    enabled: !!id,
    refetchInterval: (query) =>
      query.state.data && isInFlight(query.state.data.status) ? 2000 : false,
  });
}

export function useBookStats() {
  return useQuery({
    queryKey: qk.bookStats(),
    queryFn: getBookStats,
  });
}

export function useBookActivity(days = 7) {
  return useQuery({
    queryKey: qk.bookActivity(days),
    queryFn: () => getBookActivity(days),
  });
}

export function useCreateBook() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (request: CreateBookRequest) => createBook(request),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.books() });
      qc.invalidateQueries({ queryKey: qk.bookStats() });
    },
  });
}

export function useDeleteBook() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteBook(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.all });
    },
  });
}
