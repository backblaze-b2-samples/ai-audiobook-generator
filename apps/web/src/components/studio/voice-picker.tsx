"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useVoices } from "@/lib/queries";

interface VoicePickerProps {
  value: string;
  onChange: (voiceId: string) => void;
}

export function VoicePicker({ value, onChange }: VoicePickerProps) {
  const { data: voices, isLoading, error } = useVoices();

  if (isLoading) return <Skeleton className="h-9 w-full" />;

  if (error || !voices || voices.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Voices unavailable — check that your TTS provider key is configured.
      </p>
    );
  }

  return (
    <Select value={value || voices[0].id} onValueChange={onChange}>
      <SelectTrigger className="w-full">
        <SelectValue placeholder="Pick a narrator voice" />
      </SelectTrigger>
      <SelectContent>
        {voices.map((v) => (
          <SelectItem key={v.id} value={v.id}>
            {v.name}
            {v.description ? ` — ${v.description}` : ""}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
