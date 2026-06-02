"use client";

import { useState } from "react";
import { Download, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/error-state";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { GeneratingLoader } from "@/components/ui/generating-loader";
import { StatusBadge } from "@/components/library/status-badge";
import { ChapterPlayer } from "@/components/library/chapter-player";
import { ApiError, getMasterDownloadUrl } from "@/lib/api-client";
import { useBook, useDeleteBook } from "@/lib/queries";

interface AudiobookDetailProps {
  bookId: string;
  onDeleted: () => void;
}

export function AudiobookDetail({ bookId, onDeleted }: AudiobookDetailProps) {
  const { data: book, isLoading, error, refetch } = useBook(bookId);
  const deleteBook = useDeleteBook();
  const [confirmOpen, setConfirmOpen] = useState(false);

  if (isLoading) return <Skeleton className="h-80 w-full" />;
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (!book) return null;

  const inFlight =
    book.status === "pending" || book.status === "rendering" || book.status === "assembling";

  const onDownload = async () => {
    try {
      const { url } = await getMasterDownloadUrl(book.id);
      window.open(url, "_blank");
    } catch (err) {
      const detail = err instanceof ApiError ? err.message : "Master not ready yet";
      toast.error(detail);
    }
  };

  const onDelete = () => {
    deleteBook.mutate(book.id, {
      onSuccess: () => {
        toast.success(`${book.title} deleted`);
        onDeleted();
      },
      onError: (err) => {
        const detail = err instanceof ApiError ? err.message : "Failed to delete";
        toast.error(detail);
      },
      onSettled: () => setConfirmOpen(false),
    });
  };

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-3 border-b border-border py-4 px-5 space-y-0">
          <div className="min-w-0 space-y-1">
            <CardTitle className="card-title truncate">{book.title}</CardTitle>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <StatusBadge status={book.status} />
              <span>
                {book.chapters_rendered}/{book.chapter_count} chapters · {book.duration_human}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Button
              variant="outline"
              size="sm"
              className="h-8"
              onClick={onDownload}
              disabled={!book.master_key}
            >
              <Download className="h-3.5 w-3.5" />
              Master
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-8 text-destructive"
              onClick={() => setConfirmOpen(true)}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-5 space-y-4">
          {inFlight && (
            <div className="flex items-center gap-3 rounded-md border border-border bg-muted/30 p-3">
              <GeneratingLoader size="sm" />
              <span className="text-sm text-muted-foreground">
                Narrating chapters… this updates automatically.
              </span>
            </div>
          )}
          {book.status === "failed" && book.error && (
            <p className="text-sm text-destructive">{book.error}</p>
          )}
          {book.status === "complete" && book.error && (
            <p className="text-xs text-muted-foreground">{book.error}</p>
          )}
          <ChapterPlayer bookId={book.id} chapters={book.chapters} />
        </CardContent>
      </Card>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete audiobook?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes <strong>{book.title}</strong> — its source, all
              chapter audio, and the master — from B2. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={onDelete}
              disabled={deleteBook.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteBook.isPending ? "Deleting…" : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
