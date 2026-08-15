import { AlertIcon } from "@/components/ui";
import type { Job } from "@/lib/types";
import { JobProgress } from "./JobProgress";
import { ResultCard } from "./ResultCard";

/** Cards as they land, what was skipped, and what is still coming. */
export function ResultsPanel({ job }: Readonly<{ job: Job | null }>) {
  if (!job) return <EmptyState />;

  const running = job.status === "queued" || job.status === "running";
  const pending = Math.max(0, job.faces - job.results.length);

  return (
    <div className="flex flex-col gap-5">
      <JobProgress job={job} />

      {(job.unresolved.length > 0 || job.unsupported.length > 0) && <SkippedNotice job={job} />}

      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        {job.results.map((result, index) => (
          <ResultCard key={`${result.name}-${index}`} result={result} />
        ))}
        {running &&
          Array.from({ length: pending }).map((_, index) => (
            <div
              key={`pending-${index}`}
              aria-hidden
              className="aspect-[5/7] animate-pulse rounded-panel border border-rule bg-raised"
            />
          ))}
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-panel border border-dashed border-rule px-6 py-16 text-center">
      <h2 className="font-display text-base font-semibold">Nothing generated yet</h2>
      <p className="mx-auto mt-2 max-w-sm text-sm text-ink-soft">
        Paste a decklist and pick a mode. Cards appear here one at a time as they finish — each
        one is two AI calls, so a full deck takes a while.
      </p>
    </div>
  );
}

/** Neither list costs a credit, and both are invisible unless they are shown. */
function SkippedNotice({ job }: Readonly<{ job: Job }>) {
  return (
    <div className="flex gap-3 rounded-control border border-accent/40 bg-accent/10 p-4 text-sm">
      <AlertIcon className="mt-0.5 size-4 shrink-0 text-accent-lit" />
      <div>
        <h3 className="font-medium">Skipped before generating</h3>
        <ul className="mt-2 flex flex-col gap-1 text-ink-soft">
          {job.unresolved.map((name) => (
            <li key={name}>
              <span className="text-ink">{name}</span> — Scryfall does not know this card
            </li>
          ))}
          {job.unsupported.map((card) => (
            <li key={card.name}>
              <span className="text-ink">{card.name}</span> — the {card.layout} layout is not
              supported
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
