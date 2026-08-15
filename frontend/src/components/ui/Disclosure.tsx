import { ChevronIcon } from "./icons";

/**
 * Progressive disclosure, on `<details>` so it works before hydration and needs no ARIA of our
 * own. A decklist and a mode are all most runs need; everything else is tuning and stays folded.
 */
export function Disclosure({
  summary,
  aside,
  children,
}: Readonly<{ summary: string; aside?: string; children: React.ReactNode }>) {
  return (
    <details className="group overflow-hidden rounded-control border border-rule bg-raised/50">
      <summary
        className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 px-4 py-2.5
          text-sm font-medium transition-colors duration-[--duration-fast] hover:text-accent-lit"
      >
        <span>{summary}</span>
        <span className="flex items-center gap-2">
          {aside && <span className="hidden text-xs text-ink-soft sm:inline">{aside}</span>}
          <ChevronIcon className="size-4 text-ink-soft transition-transform duration-[--duration-base] ease-[--ease-out] group-open:rotate-180" />
        </span>
      </summary>
      <div className="border-t border-rule p-4 sm:p-5">{children}</div>
    </details>
  );
}
