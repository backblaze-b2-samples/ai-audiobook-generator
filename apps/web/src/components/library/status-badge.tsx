"use client";

import { Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { NarrationStatus } from "@ai-audiobook-generator/shared";

const LABELS: Record<NarrationStatus, string> = {
  pending: "Queued",
  rendering: "Rendering",
  assembling: "Assembling",
  complete: "Complete",
  failed: "Failed",
};

const VARIANTS: Record<NarrationStatus, "default" | "secondary" | "outline" | "destructive"> = {
  pending: "secondary",
  rendering: "secondary",
  assembling: "secondary",
  complete: "default",
  failed: "destructive",
};

export function StatusBadge({ status }: { status: NarrationStatus }) {
  const inFlight = status === "pending" || status === "rendering" || status === "assembling";
  return (
    <Badge variant={VARIANTS[status]} className="gap-1">
      {inFlight && <Loader2 className="h-3 w-3 animate-spin" />}
      {LABELS[status]}
    </Badge>
  );
}
