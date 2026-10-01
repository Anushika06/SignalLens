import { cn } from "@/lib/utils";

/** A lens with a signal trace inside it. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={cn("size-6 shrink-0", className)}>
      <rect width="24" height="24" rx="6" className="fill-primary" />
      <circle cx="10.75" cy="10.75" r="5.25" fill="none" stroke="white" strokeWidth="1.8" />
      <path d="M14.6 14.6 18.5 18.5" stroke="white" strokeWidth="2" strokeLinecap="round" />
      <path
        d="M7.3 10.9h1.4l1-2.2 1.5 4.3 1-2.1h1.3"
        fill="none"
        stroke="white"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 text-[15px] font-semibold tracking-tight", className)}>
      <LogoMark />
      SignalLens
    </span>
  );
}
