import { DownloadIcon } from "@/components/ui";
import type { CardResult } from "@/lib/types";
import { duration } from "./JobProgress";

/** One finished face: the card and a way to get it out.
 *
 * Grading (Sound/Unsound + problem codes) is hidden for the Milestone 1 demo UI — the checks
 * still run on the backend and stay in the job payload; we just do not surface them here yet.
 */
export function ResultCard({ result }: Readonly<{ result: CardResult }>) {
  return (
    <figure className="flex flex-col gap-3">
      {result.image ? (
        // eslint-disable-next-line @next/next/no-img-element -- generated files, not static assets
        <img
          src={result.image}
          alt={`${result.name}, generated`}
          // 5:7 is the printed card ratio, reserved before the file arrives so the grid does not
          // jump as each card lands (CLS).
          className="aspect-[5/7] w-full rounded-panel border border-rule bg-raised object-cover"
        />
      ) : (
        <div className="grid aspect-[5/7] place-items-center rounded-panel border border-dashed border-edge bg-raised px-4 text-center text-sm text-ink-soft">
          No image was produced
        </div>
      )}

      <figcaption className="flex flex-col gap-2">
        <span className="text-sm font-medium">
          {result.quantity > 1 && <span className="text-ink-soft">{result.quantity}× </span>}
          {result.name}
          {result.seconds !== undefined && (
            <span className="ml-2 text-xs font-normal text-ink-soft">
              {duration(result.seconds)}
            </span>
          )}
        </span>

        {result.status === "failed" && result.problems.length > 0 && (
          <ul className="flex flex-col gap-1">
            {result.problems.map((problem) => (
              <li key={problem.code} className="text-xs text-ink-soft">
                <code className="text-fault">{problem.code}</code> {problem.detail}
              </li>
            ))}
          </ul>
        )}

        {result.image && (
          <a
            href={result.image}
            download
            className="inline-flex min-h-11 items-center gap-1.5 text-xs font-medium text-accent-lit
              transition-colors duration-[--duration-fast] hover:text-ink"
          >
            <DownloadIcon className="size-3.5" />
            Download full resolution
          </a>
        )}
      </figcaption>
    </figure>
  );
}
