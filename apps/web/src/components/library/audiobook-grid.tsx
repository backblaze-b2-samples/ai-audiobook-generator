"use client";

import { BookAudio } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { StatusBadge } from "@/components/library/status-badge";
import { useBooks } from "@/lib/queries";
import { formatDate } from "@/lib/utils";

interface AudiobookGridProps {
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function AudiobookGrid({ selectedId, onSelect }: AudiobookGridProps) {
  const { data: books = [], isLoading, error, refetch } = useBooks();

  if (isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-28 w-full" />
        ))}
      </div>
    );
  }

  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;

  if (books.length === 0) {
    return (
      <EmptyState
        icon={BookAudio}
        title="No audiobooks yet"
        description="Create one from the New Audiobook page to get started."
      />
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {books.map((book) => {
        const isActive = book.id === selectedId;
        return (
          <Card
            key={book.id}
            role="button"
            tabIndex={0}
            onClick={() => onSelect(book.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect(book.id);
              }
            }}
            className={`card-hover cursor-pointer ${isActive ? "ring-2 ring-primary" : ""}`}
          >
            <CardContent className="p-4 space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="stat-icon-wrap">
                    <BookAudio className="h-4 w-4" />
                  </div>
                  <span className="font-medium truncate">{book.title}</span>
                </div>
                <StatusBadge status={book.status} />
              </div>
              <div className="flex items-center justify-between text-xs text-muted-foreground tabular-nums">
                <span>
                  {book.chapters_rendered}/{book.chapter_count} chapters
                </span>
                <span>{book.duration_human}</span>
                <span>{formatDate(book.created_at)}</span>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
