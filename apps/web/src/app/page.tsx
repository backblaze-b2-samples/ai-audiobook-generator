import Link from "next/link";
import { Mic } from "lucide-react";

import { Button } from "@/components/ui/button";
import { StatsCards } from "@/components/dashboard/stats-cards";
import { RecentAudiobooksTable } from "@/components/dashboard/recent-audiobooks-table";
import { NarrationChart } from "@/components/dashboard/narration-chart";

export default function DashboardPage() {
  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-1.5">
            Your audiobook library and narration activity, backed by Backblaze B2.
          </p>
        </div>
        <Button asChild size="sm" className="h-8">
          <Link href="/create">
            <Mic className="h-3.5 w-3.5" />
            New audiobook
          </Link>
        </Button>
      </div>
      <StatsCards />
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="animate-fade-in-up stagger-3">
          <NarrationChart />
        </div>
        <div className="animate-fade-in-up stagger-4">
          <RecentAudiobooksTable />
        </div>
      </div>
    </div>
  );
}
