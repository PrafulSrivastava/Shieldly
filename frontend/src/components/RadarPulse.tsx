"use client";

export function RadarPulse({ accelerate = false }: { accelerate?: boolean }) {
  const dur = accelerate ? "2.5s" : "4s";

  return (
    <div className="absolute inset-0 flex items-center justify-center pointer-events-none overflow-hidden">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="absolute rounded-full border border-coral/[0.08]"
          style={{
            width: 520,
            height: 520,
            animationName: "radar-pulse",
            animationDuration: dur,
            animationTimingFunction: "ease-out",
            animationIterationCount: "infinite",
            animationDelay: `${i * (parseFloat(dur) / 3)}s`,
          }}
        />
      ))}
    </div>
  );
}
