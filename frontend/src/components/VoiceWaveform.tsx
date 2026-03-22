"use client";

import { useEffect, useRef, useState } from "react";

interface Props {
  isSpeaking: boolean;
  compact?: boolean;
}

const BAR_COUNT = 5;
const COMPACT_BAR_COUNT = 3;

export function VoiceWaveform({ isSpeaking, compact }: Props) {
  const barCount = compact ? COMPACT_BAR_COUNT : BAR_COUNT;
  const minH = compact ? 4 : 6;
  const maxH = compact ? 20 : 48;

  const [heights, setHeights] = useState<number[]>(
    Array(barCount).fill(minH),
  );
  const rafRef = useRef<number>(0);
  const targetRef = useRef<number[]>(Array(barCount).fill(minH));
  const currentRef = useRef<number[]>(Array(barCount).fill(minH));

  useEffect(() => {
    if (currentRef.current.length !== barCount) {
      currentRef.current = Array(barCount).fill(minH);
      targetRef.current = Array(barCount).fill(minH);
    }

    const retarget = () => {
      targetRef.current = Array.from({ length: barCount }, () =>
        isSpeaking ? minH + Math.random() * (maxH - minH) : minH,
      );
    };

    const interval = setInterval(retarget, isSpeaking ? 120 : 300);
    retarget();

    const animate = () => {
      const lerp = isSpeaking ? 0.18 : 0.12;
      currentRef.current = currentRef.current.map(
        (v, i) => v + (targetRef.current[i] - v) * lerp,
      );
      setHeights([...currentRef.current]);
      rafRef.current = requestAnimationFrame(animate);
    };

    rafRef.current = requestAnimationFrame(animate);

    return () => {
      clearInterval(interval);
      cancelAnimationFrame(rafRef.current);
    };
  }, [isSpeaking, barCount, minH, maxH]);

  return (
    <div
      className={`flex items-end justify-center ${
        compact ? "gap-[3px] h-6" : "gap-[5px] h-14"
      }`}
    >
      {heights.map((h, i) => (
        <div
          key={i}
          className={`rounded-full bg-gradient-to-t from-coral to-coral/50 ${
            compact ? "w-[4px]" : "w-[6px]"
          }`}
          style={{ height: h, transition: "none" }}
        />
      ))}
    </div>
  );
}
