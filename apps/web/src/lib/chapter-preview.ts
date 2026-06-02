// Client-side chapter boundary estimate, mirroring the backend heuristics in
// services/api/app/service/chapters.py closely enough for a live preview. The
// server remains the source of truth — this is only a "here's roughly how it
// will split" hint while the user edits the manuscript.

export interface ChapterPreview {
  title: string;
  charCount: number;
}

const MAX_CHARS = 8000;

const HEADING_RE = /^\s{0,3}#{1,3}\s+(.+?)\s*#*\s*$/;
const CHAPTER_RE = /^\s*(?:chapter|part|book|section)\b[\s:.\-]*.*$/i;
const RULE_RE = /^\s*([-*_])\1{2,}\s*$/;

function markerTitle(line: string): string | null {
  const heading = line.match(HEADING_RE);
  if (heading) return heading[1].trim();
  if (CHAPTER_RE.test(line) && line.trim().length <= 80) return line.trim();
  if (RULE_RE.test(line)) return "";
  return null;
}

export function previewChapters(text: string): ChapterPreview[] {
  const normalized = text.replace(/\r\n/g, "\n").trim();
  if (!normalized) return [];

  const marked = splitByMarkers(normalized);
  if (marked.length <= 1 && normalized.length > MAX_CHARS) {
    return splitBySize(normalized);
  }
  if (marked.length === 0) return splitBySize(normalized);
  return marked.map((c, i) => ({
    title: c.title || `Chapter ${i + 1}`,
    charCount: c.charCount,
  }));
}

function splitByMarkers(text: string): ChapterPreview[] {
  const chapters: ChapterPreview[] = [];
  let title = "";
  let body: string[] = [];
  const flush = () => {
    const joined = body.join("\n").trim();
    if (joined) chapters.push({ title, charCount: joined.length });
  };
  for (const line of text.split("\n")) {
    const marker = markerTitle(line);
    if (marker !== null) {
      flush();
      title = marker;
      body = [];
    } else {
      body.push(line);
    }
  }
  flush();
  return chapters;
}

function splitBySize(text: string): ChapterPreview[] {
  const paragraphs = text
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);
  const chapters: ChapterPreview[] = [];
  let buf: string[] = [];
  let size = 0;
  const flush = () => {
    const joined = buf.join("\n\n").trim();
    if (joined) chapters.push({ title: `Chapter ${chapters.length + 1}`, charCount: joined.length });
  };
  for (const para of paragraphs) {
    if (buf.length > 0 && size + para.length > MAX_CHARS) {
      flush();
      buf = [];
      size = 0;
    }
    buf.push(para);
    size += para.length;
  }
  flush();
  return chapters;
}
