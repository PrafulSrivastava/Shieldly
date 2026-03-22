"use client";

import { useRef, useEffect } from "react";

interface TranscriptLine {
  role: "agent" | "user";
  text: string;
  ts: number;
}

interface Props {
  lines: TranscriptLine[];
}

export function TranscriptionFeed({ lines }: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines.length]);

  return (
    <div className="relative w-full max-w-sm">
      <div className="max-h-28 overflow-y-auto scrollbar-thin px-1">
        <div className="font-body text-[12px] leading-[1.7] space-y-0.5">
          {lines.length === 0 && (
            <span className="text-warm-muted/40 animate-blink">
              Awaiting agent...
            </span>
          )}
          {lines.map((line, i) => (
            <div
              key={i}
              className={`animate-slide-up ${
                line.role === "agent" ? "text-coral" : "text-warm-muted"
              }`}
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
      <div className="absolute top-0 left-0 right-0 h-3 bg-gradient-to-b from-bg/90 to-transparent pointer-events-none" />
    </div>
  );
}
