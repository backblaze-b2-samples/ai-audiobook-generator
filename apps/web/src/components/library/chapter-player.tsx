"use client";

import { useRef, useState } from "react";
import { Play } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ApiError, getChapterStreamUrl } from "@/lib/api-client";
import type { Chapter } from "@ai-audiobook-generator/shared";

interface ChapterPlayerProps {
  bookId: string;
  chapters: Chapter[];
}

function fmt(seconds: number | null): string {
  if (!seconds) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function ChapterPlayer({ bookId, chapters }: ChapterPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [loadingIndex, setLoadingIndex] = useState<number | null>(null);
  const [src, setSrc] = useState<string | null>(null);

  // Stream the chosen chapter inline from a presigned B2 URL (no attachment
  // disposition), letting the browser issue Range reads against B2.
  const play = async (index: number) => {
    setLoadingIndex(index);
    try {
      const { url } = await getChapterStreamUrl(bookId, index);
      setSrc(url);
      setActiveIndex(index);
      // Wait a tick for the <audio> src to update, then play.
      requestAnimationFrame(() => {
        audioRef.current?.load();
        audioRef.current?.play().catch(() => undefined);
      });
    } catch (err) {
      const detail = err instanceof ApiError ? err.message : "Could not load chapter audio";
      toast.error(detail);
    } finally {
      setLoadingIndex(null);
    }
  };

  return (
    <div className="space-y-3">
      <audio ref={audioRef} controls src={src ?? undefined} className="w-full" />
      <ul className="divide-y divide-border rounded-md border border-border">
        {chapters.map((c) => {
          const ready = c.status === "complete" && !!c.audio_key;
          const isActive = c.index === activeIndex;
          return (
            <li
              key={c.index}
              className={`flex items-center gap-3 px-4 py-2.5 text-sm ${isActive ? "bg-accent/40" : ""}`}
            >
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-7 w-7 shrink-0"
                disabled={!ready || loadingIndex === c.index}
                onClick={() => play(c.index)}
                aria-label={`Play ${c.title}`}
              >
                <Play className="h-3.5 w-3.5" />
              </Button>
              <span className="text-xs font-mono text-muted-foreground tabular-nums w-6">
                {c.index + 1}
              </span>
              <span className="truncate flex-1">{c.title}</span>
              <span className="text-xs text-muted-foreground tabular-nums whitespace-nowrap">
                {ready ? fmt(c.duration_seconds) : c.status}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
