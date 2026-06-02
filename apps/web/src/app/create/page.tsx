import { CreateForm } from "@/components/studio/create-form";

export default function CreatePage() {
  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5">
        <h1 className="page-title">New Audiobook</h1>
        <p className="text-sm text-muted-foreground mt-1.5">
          Paste or upload a manuscript, pick a narrator voice, and generate a
          chapterized audiobook stored on Backblaze B2.
        </p>
      </div>
      <div className="animate-fade-in-up stagger-2">
        <CreateForm />
      </div>
    </div>
  );
}
