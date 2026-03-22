"use client";

import { useState, useCallback } from "react";

interface Props {
  onTrigger: () => void | Promise<void>;
  disabled?: boolean;
}

export function SOSButton({ onTrigger, disabled }: Props) {
  const [pressed, setPressed] = useState(false);

  const handleClick = useCallback(async () => {
    if (disabled || pressed) return;
    setPressed(true);
    try {
      await onTrigger();
    } finally {
      setTimeout(() => setPressed(false), 400);
    }
  }, [onTrigger, disabled, pressed]);

  return (
    <button
      onClick={handleClick}
      disabled={disabled}
      className="relative select-none focus:outline-none disabled:opacity-40 disabled:pointer-events-none"
    >
      {/* Outer glow ring */}
      <div
        className={`
          absolute -inset-3 rounded-full bg-danger/10 blur-xl
          transition-opacity duration-300
          ${pressed ? "opacity-80" : "opacity-40"}
        `}
      />

      {/* Main button */}
      <div
        className={`
          relative w-48 h-48 rounded-full
          bg-gradient-to-b from-danger to-danger-dark
          flex items-center justify-center
          animate-glow-pulse
          transition-transform duration-200 ease-out
          ${pressed ? "scale-[0.88]" : "scale-100 hover:scale-[1.03]"}
        `}
      >
        {/* Inner highlight */}
        <div className="absolute inset-[3px] rounded-full bg-gradient-to-b from-white/[0.08] to-transparent pointer-events-none" />

        <span className="font-display text-[22px] tracking-[4px] text-white leading-none text-center px-6">
          I FEEL
          <br />
          UNSAFE
        </span>
      </div>
    </button>
  );
}
