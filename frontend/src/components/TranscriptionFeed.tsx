"use client";

import { useRef, useEffect } from "react";

interface TranscriptLine {
  role: "agent" | "user";
  text: string;
  ts: number;
}

interface Props {
  lines: TranscriptLine[];
  compact?: boolean;
}

export function TranscriptionFeed({ lines, compact }: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines.length]);

  return (
    <div className={`relative w-full ${compact ? "max-w-[200px]" : "max-w-sm"}`}>
      <div
        className={`overflow-y-auto scrollbar-thin px-1 ${
          compact ? "max-h-14" : "max-h-28"
        }`}
      >
        <div
          className={`font-body leading-[1.7] space-y-0.5 ${
            compact ? "text-[10px]" : "text-[12px]"
          }`}
        >
          {lines.length === 0 && (
            <span className="text-warm-muted/40 animate-blink">
              {compact ? "Listening..." : "Awaiting agent..."}
            </span>
          )}
          {lines.map((line, i) => (
            <div
              key={i}
              className={`animate-slide-up ${
                line.role === "agent" ? "text-coral" : "text-warm-muted"
              } ${compact ? "truncate" : ""}`}
            >
              <span className="text-plum/25 mr-1.5 select-none">
                {line.role === "agent" ? "\u25B8" : "\u25B9"}
              </span>
              {line.text}
            </div>
          ))}
          <div ref={endRef} />
        </div>
      </div>

      {/* Top fade */}
      <div
        className={`absolute top-0 left-0 right-0 bg-gradient-to-b pointer-events-none ${
          compact
            ? "h-2 from-white/90 to-transparent"
            : "h-3 from-bg/90 to-transparent"
        }`}
      />
    </div>
  );
}
