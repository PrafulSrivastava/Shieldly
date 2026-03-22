"use client";

interface Props {
  count: number;
}

export function ShieldCounter({ count }: Props) {
  const dot =
    count >= 5 ? "bg-shield" : count >= 2 ? "bg-amber" : "bg-danger";
  const text =
    count >= 5
      ? "text-shield"
      : count >= 2
        ? "text-amber"
        : "text-danger";

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-void-light/80 backdrop-blur-sm border border-void-border">
      <span className={`w-1.5 h-1.5 rounded-full ${dot} animate-dot-pulse`} />
      <span className={`font-mono text-[10px] tracking-[1.5px] ${text}`}>
        {count} SHIELD{count !== 1 ? "S" : ""} NEARBY
      </span>
    </div>
  );
}
