"use client";

import { useState } from "react";
import { X } from "lucide-react";

import { cn } from "@/lib/utils";

type TagInputProps = {
  id?: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  "aria-describedby"?: string;
  "aria-invalid"?: boolean;
};

/**
 * A list of short values edited as chips. Enter or comma adds, Backspace on an empty field
 * removes the last chip, pasting "a, b, c" adds all three. Duplicates are ignored.
 */
export function TagInput({ id, value, onChange, placeholder, disabled, className, ...aria }: TagInputProps) {
  const [draft, setDraft] = useState("");

  function add(raw: string) {
    const incoming = raw
      .split(/[,\n]/)
      .map((item) => item.trim())
      .filter(Boolean);
    if (incoming.length === 0) return;
    const seen = new Set(value.map((item) => item.toLowerCase()));
    const next = [...value];
    for (const item of incoming) {
      if (!seen.has(item.toLowerCase())) {
        seen.add(item.toLowerCase());
        next.push(item);
      }
    }
    onChange(next);
    setDraft("");
  }

  function remove(index: number) {
    onChange(value.filter((_, i) => i !== index));
  }

  return (
    <div
      className={cn(
        "flex min-h-8 w-full flex-wrap items-center gap-1 rounded-lg border border-input bg-transparent px-1.5 py-1 transition-colors focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50 dark:bg-input/30",
        aria["aria-invalid"] && "border-destructive ring-3 ring-destructive/20",
        disabled && "pointer-events-none opacity-50",
        className,
      )}
    >
      {value.map((item, index) => (
        <span
          key={`${item}-${index}`}
          className="inline-flex h-6 max-w-full items-center gap-1 rounded-md bg-secondary pr-0.5 pl-2 text-xs font-medium text-secondary-foreground"
        >
          <span className="truncate">{item}</span>
          <button
            type="button"
            onClick={() => remove(index)}
            disabled={disabled}
            className="flex size-5 items-center justify-center rounded-sm text-muted-foreground hover:bg-background hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            aria-label={`Remove ${item}`}
          >
            <X className="size-3" aria-hidden="true" />
          </button>
        </span>
      ))}
      <input
        id={id}
        value={draft}
        disabled={disabled}
        placeholder={value.length === 0 ? placeholder : undefined}
        onChange={(event) => {
          const text = event.target.value;
          if (text.includes(",")) add(text);
          else setDraft(text);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            add(draft);
          } else if (event.key === "Backspace" && draft === "" && value.length > 0) {
            remove(value.length - 1);
          }
        }}
        onPaste={(event) => {
          const text = event.clipboardData.getData("text");
          if (/[,\n]/.test(text)) {
            event.preventDefault();
            add(draft + text);
          }
        }}
        onBlur={() => add(draft)}
        className="h-6 min-w-24 flex-1 bg-transparent px-1 text-base outline-none placeholder:text-muted-foreground md:text-sm"
        aria-describedby={aria["aria-describedby"]}
        aria-invalid={aria["aria-invalid"]}
      />
    </div>
  );
}
