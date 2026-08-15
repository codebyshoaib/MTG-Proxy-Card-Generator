import type { Job } from "@/lib/types";

/**
 * How far in, and how much longer.
 *
 * A generation is minutes long, so a spinner is not feedback — it is an unanswered question. The
 * bar is fed by finished faces and the estimate comes from the backend, which knows how many
 * faces run at once and how long the finished ones actually took.
 */
export function JobProgress({ job }: Readonly<{ job: Job }>) {
  const done = job.results.length;
  const share = job.faces ? done / job.faces : 0;
  const running = job.status === "queued" || job.status === "running";

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 className="font-display text-base font-semibold">
          {running ? "Generating" : "Cards"}
        </h2>
        <p className="text-sm text-ink-soft" role="status">
          {done} of {job.faces} {job.faces === 1 ? "face" : "faces"}
          {running && job.eta_seconds !== null && (
            <span> · about {duration(job.eta_seconds)} left</span>
          )}
          {running && job.workers > 1 && (
            <span className="text-ink-soft/70"> · {job.workers} at a time</span>
          )}
          {job.status === "failed" && job.error && (
            <span className="text-fault"> · {job.error}</span>
          )}
        </p>
      </div>

      <div
        // The numbers live in the status line above, which is the live region; this bar is the
        // same information drawn, so it is hidden from screen readers rather than announced twice.
        aria-hidden
        className="h-1.5 overflow-hidden rounded-full bg-raised"
      >
        <div
          className="h-full rounded-full bg-accent transition-[width] duration-500 ease-[--ease-out]"
          style={{ width: `${Math.round(share * 100)}%` }}
        />
      </div>
    </div>
  );
}

/** Whole minutes once past a minute — a card takes ~45s, so "3m" is as precise as honest. */
export function duration(seconds: number) {
  if (seconds < 60) return `${Math.max(5, Math.round(seconds / 5) * 5)}s`;
  return `${Math.round(seconds / 60)}m`;
}
