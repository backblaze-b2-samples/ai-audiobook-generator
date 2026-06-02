"use client";

import { useMemo } from "react";
import { ListMusic } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { EmptyState } from "@/components/ui/empty-state";
import { previewChapters } from "@/lib/chapter-preview";

export function ChapterPreview({ text }: { text: string }) {
  const chapters = useMemo(() => previewChapters(text), [text]);

  return (
    <Card>
      <CardHeader className="border-b border-border py-4 px-5">
        <CardTitle className="card-title">
          Detected Chapters
          {chapters.length > 0 && (
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              {chapters.length} estimated
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {chapters.length === 0 ? (
          <EmptyState
            icon={ListMusic}
            title="No chapters yet"
            description="Paste or type a manuscript to see how it will split."
          />
        ) : (
          <ScrollArea className="h-[320px]">
            <ul className="divide-y divide-border">
              {chapters.map((c, i) => (
                <li
                  key={i}
                  className="flex items-center justify-between gap-3 px-5 py-2.5 text-sm"
                >
                  <span className="flex items-center gap-2 truncate">
                    <span className="text-xs font-mono text-muted-foreground tabular-nums w-6">
                      {i + 1}
                    </span>
                    <span className="truncate">{c.title}</span>
                  </span>
                  <span className="text-xs text-muted-foreground tabular-nums whitespace-nowrap">
                    {c.charCount.toLocaleString()} chars
                  </span>
                </li>
              ))}
            </ul>
          </ScrollArea>
        )}
        <p className="px-5 py-3 text-xs text-muted-foreground border-t border-border">
          This is an estimate. The server re-splits on the same rules when you generate.
        </p>
      </CardContent>
    </Card>
  );
}
