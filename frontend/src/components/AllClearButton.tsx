"use client";

import { useState, useRef, useCallback } from "react";

interface Props {
  onConfirm: () => void | Promise<void>;
}

const HOLD_MS = 2_000;
const CIRCUMFERENCE = 2 * Math.PI * 38;

export function AllClearButton({ onConfirm }: Props) {
  const [holding, setHolding] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  const handleDown = useCallback(() => {
    if (confirmed) return;
    setHolding(true);
    timerRef.current = setTimeout(async () => {
      setConfirmed(true);
      await onConfirm();
    }, HOLD_MS);
  }, [onConfirm, confirmed]);

  const handleUp = useCallback(() => {
    if (confirmed) return;
    setHolding(false);
    clearTimeout(timerRef.current);
  }, [confirmed]);

  if (confirmed) {
    return (
      <div className="w-[72px] h-[72px] rounded-full bg-shield/10 border border-shield/40 flex items-center justify-center animate-fade-in">
        <span className="font-display text-sm text-shield tracking-[3px]">
          SAFE
        </span>
      </div>
    );
  }

  return (
    <button
      onPointerDown={handleDown}
      onPointerUp={handleUp}
      onPointerLeave={handleUp}
      onContextMenu={(e) => e.preventDefault()}
      className="relative w-[72px] h-[72px] rounded-full border border-white/15 flex items-center justify-center group select-none touch-none"
    >
      {/* Progress ring */}
      <svg
        className="absolute inset-0 w-full h-full -rotate-90 pointer-events-none"
        viewBox="0 0 80 80"
      >
        <circle
          cx="40"
          cy="40"
          r="38"
          fill="none"
          stroke="rgba(0,230,118,0.25)"
          strokeWidth="2"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={holding ? 0 : CIRCUMFERENCE}
          strokeLinecap="round"
          style={{
            transition: holding
              ? `stroke-dashoffset ${HOLD_MS}ms linear`
              : "stroke-dashoffset 0.15s ease",
          }}
        />
      </svg>

      <span className="font-display text-[10px] text-white/50 tracking-[2px] group-active:text-shield/80 transition-colors leading-none text-center">
        ALL
        <br />
        CLEAR
      </span>
    </button>
  );
}
