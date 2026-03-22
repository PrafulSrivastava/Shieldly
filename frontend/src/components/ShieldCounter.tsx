"use client";

interface Props {
  count: number;
}

export function ShieldCounter({ count }: Props) {
  const bgColor =
    count >= 5 ? "bg-sage-light" : count >= 2 ? "bg-blush" : "bg-lavender";
  const dotColor =
    count >= 5 ? "bg-sage" : count >= 2 ? "bg-coral" : "bg-plum";
  const textColor =
    count >= 5
      ? "text-plum"
      : count >= 2
        ? "text-coral"
        : "text-plum";

  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-pill ${bgColor} border border-lavender-muted`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dotColor} animate-dot-pulse`} />
      <span className={`font-body text-[10px] tracking-[0.12em] font-semibold uppercase ${textColor}`}>
        {count} Shield{count !== 1 ? "s" : ""} Nearby
      </span>
    </div>
  );
}
