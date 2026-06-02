"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Mic } from "lucide-react";

import { Button } from "@/components/ui/button";
import { AudiobookGrid } from "@/components/library/audiobook-grid";
import { AudiobookDetail } from "@/components/library/audiobook-detail";

function LibraryView() {
  const params = useSearchParams();
  const initial = params.get("book");
  const [selectedId, setSelectedId] = useState<string | null>(initial);

  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="page-title">Library</h1>
          <p className="text-sm text-muted-foreground mt-1.5">
            Your audiobooks, scoped to the <code>audiobooks/</code> prefix. Stream
            chapters inline or download the master.
          </p>
        </div>
        <Button asChild size="sm" className="h-8">
          <Link href="/create">
            <Mic className="h-3.5 w-3.5" />
            New audiobook
          </Link>
        </Button>
      </div>

      {selectedId && (
        <div className="animate-fade-in-up">
          <AudiobookDetail bookId={selectedId} onDeleted={() => setSelectedId(null)} />
        </div>
      )}

      <div className="animate-fade-in-up stagger-2">
        <AudiobookGrid selectedId={selectedId} onSelect={setSelectedId} />
      </div>
    </div>
  );
}

export default function LibraryPage() {
  return (
    <Suspense fallback={null}>
      <LibraryView />
    </Suspense>
  );
}
