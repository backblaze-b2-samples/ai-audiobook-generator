"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Mic, Upload } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { VoicePicker } from "@/components/studio/voice-picker";
import { ChapterPreview } from "@/components/studio/chapter-preview";
import { ApiError } from "@/lib/api-client";
import { useCreateBook } from "@/lib/queries";

export function CreateForm() {
  const router = useRouter();
  const createBook = useCreateBook();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [voiceId, setVoiceId] = useState("");

  const canSubmit = title.trim().length > 0 && text.trim().length > 0 && !createBook.isPending;

  const onPickFile = async (file: File | undefined) => {
    if (!file) return;
    if (!file.type.startsWith("text/") && !file.name.endsWith(".txt") && !file.name.endsWith(".md")) {
      toast.error("Please choose a plain-text (.txt or .md) manuscript.");
      return;
    }
    const content = await file.text();
    setText(content);
    if (!title.trim()) {
      setTitle(file.name.replace(/\.[^.]+$/, ""));
    }
  };

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    createBook.mutate(
      { title: title.trim(), text, voice_id: voiceId || undefined },
      {
        onSuccess: (book) => {
          toast.success("Narration started");
          router.push(`/library?book=${book.id}`);
        },
        onError: (err) => {
          const detail = err instanceof ApiError ? err.message : "Failed to start narration";
          toast.error(detail);
        },
      },
    );
  };

  return (
    <form onSubmit={onSubmit} className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
      <div className="space-y-6">
        <Card>
          <CardHeader className="border-b border-border py-4 px-5">
            <CardTitle className="card-title">Manuscript</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 p-5">
            <div className="space-y-2">
              <Label htmlFor="title">Title</Label>
              <Input
                id="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="The Time Machine"
                maxLength={200}
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="text">Text</Label>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload className="h-3.5 w-3.5 mr-1" />
                  Load .txt / .md
                </Button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".txt,.md,text/plain,text/markdown"
                  className="hidden"
                  onChange={(e) => onPickFile(e.target.files?.[0])}
                />
              </div>
              <Textarea
                id="text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste your manuscript here. Use 'Chapter N', Markdown headings, or '---' to mark chapter boundaries."
                className="min-h-[280px] font-mono text-sm"
              />
              <p className="text-xs text-muted-foreground">
                {text.length.toLocaleString()} characters
              </p>
            </div>

            <div className="space-y-2">
              <Label>Narrator voice</Label>
              <VoicePicker value={voiceId} onChange={setVoiceId} />
              <p className="text-xs text-muted-foreground">
                The whole book is narrated in one voice. Multi-voice narration is a future enhancement.
              </p>
            </div>

            <Button type="submit" disabled={!canSubmit} className="w-full">
              <Mic className="h-4 w-4" />
              {createBook.isPending ? "Starting…" : "Generate audiobook"}
            </Button>
          </CardContent>
        </Card>
      </div>

      <ChapterPreview text={text} />
    </form>
  );
}
