export type FileStatus = "uploading" | "complete" | "error";

export interface FileMetadata {
  key: string;
  filename: string;
  folder: string;
  size_bytes: number;
  size_human: string;
  content_type: string;
  uploaded_at: string;
  url: string | null;
}

export interface FileMetadataDetail {
  filename: string;
  size_bytes: number;
  size_human: string;
  mime_type: string;
  extension: string;
  md5: string;
  sha256: string;
  uploaded_at: string;
  // PDF-specific (ebook manuscript sources)
  pdf_pages: number | null;
  pdf_author: string | null;
  pdf_title: string | null;
  // Audio (chapter renders + master)
  duration_seconds: number | null;
  codec: string | null;
  bitrate: number | null;
}

export interface FileUploadResponse {
  key: string;
  filename: string;
  size_bytes: number;
  size_human: string;
  content_type: string;
  uploaded_at: string;
  url: string | null;
  metadata: FileMetadataDetail | null;
}

export interface DailyUploadCount {
  date: string;
  uploads: number;
}

export interface UploadStats {
  total_files: number;
  total_size_bytes: number;
  total_size_human: string;
  uploads_today: number;
  total_downloads: number;
}

// ----- Audiobook domain (mirrors services/api/app/types/books.py) -----

export type NarrationStatus =
  | "pending"
  | "rendering"
  | "assembling"
  | "complete"
  | "failed";

export interface Voice {
  id: string;
  name: string;
  description: string | null;
}

export interface Chapter {
  index: number;
  title: string;
  char_count: number;
  status: NarrationStatus;
  audio_key: string | null;
  duration_seconds: number | null;
  error: string | null;
}

export interface Book {
  id: string;
  title: string;
  status: NarrationStatus;
  voice_id: string;
  chapter_count: number;
  chapters_rendered: number;
  duration_seconds: number;
  duration_human: string;
  master_key: string | null;
  created_at: string;
  updated_at: string;
  error: string | null;
  chapters: Chapter[];
}

export interface BookSummary {
  id: string;
  title: string;
  status: NarrationStatus;
  chapter_count: number;
  chapters_rendered: number;
  duration_seconds: number;
  duration_human: string;
  created_at: string;
}

export interface CreateBookRequest {
  title: string;
  text: string;
  voice_id?: string;
}

export interface BookStats {
  total_books: number;
  total_chapters: number;
  total_duration_seconds: number;
  total_duration_human: string;
  total_size_bytes: number;
  total_size_human: string;
}

export interface DailyNarrationHours {
  date: string;
  hours: number;
}

