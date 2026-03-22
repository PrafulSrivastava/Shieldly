"use client";

import { useEffect, useRef, useState } from "react";

interface Props {
  isSpeaking: boolean;
}

const BAR_COUNT = 5;
const MIN_H = 6;
const MAX_H = 48;

export function VoiceWaveform({ isSpeaking }: Props) {
  const [heights, setHeights] = useState<number[]>(
    Array(BAR_COUNT).fill(MIN_H),
  );
  const rafRef = useRef<number>(0);
  const targetRef = useRef<number[]>(Array(BAR_COUNT).fill(MIN_H));
  const currentRef = useRef<number[]>(Array(BAR_COUNT).fill(MIN_H));

  useEffect(() => {
    const retarget = () => {
      targetRef.current = Array.from({ length: BAR_COUNT }, () =>
        isSpeaking ? MIN_H + Math.random() * (MAX_H - MIN_H) : MIN_H,
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
  }, [isSpeaking]);

  return (
    <div className="flex items-end justify-center gap-[5px] h-14">
      {heights.map((h, i) => (
        <div
          key={i}
          className="w-[6px] rounded-full bg-gradient-to-t from-danger to-danger/60"
          style={{ height: h, transition: "none" }}
        />
      ))}
    </div>
  );
}
