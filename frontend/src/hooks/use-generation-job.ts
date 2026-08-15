"use client";

import { useCallback, useEffect, useState } from "react";

import { getJob, RequestRejected, startJob } from "@/lib/api";
import type { GenerateRequest, Job } from "@/lib/types";

const POLL_MS = 2000;

/**
 * One job, from submit to the last card.
 *
 * The whole reason this is a poll and not a request: a Creative Full card is two AI calls and
 * about a minute, and a decklist is that times N. Nothing survives a request that long.
 */
export function useGenerationJob() {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const jobId = job?.id;
  const finished = !job || job.status === "done" || job.status === "failed";

  // The poll depends on the id and the finished flag, never on the job object — otherwise every
  // response would tear down and rebuild the interval, and a slow tick could starve it.
  useEffect(() => {
    if (!jobId || finished) return;
    const timer = setInterval(async () => {
      try {
        setJob(await getJob(jobId));
      } catch {
        // A dropped poll is not a failed job — the next tick asks again.
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [jobId, finished]);

  const start = useCallback(async (request: GenerateRequest) => {
    setSubmitting(true);
    setError(null);
    try {
      setJob(await startJob(request));
    } catch (failure) {
      setJob(null);
      setError(describe(failure));
    } finally {
      setSubmitting(false);
    }
  }, []);

  return {
    job,
    error,
    submitting,
    running: job !== null && !finished,
    start,
  };
}

/** A rejection carries its reason and the names behind it; anything else is a network fault. */
function describe(failure: unknown) {
  if (!(failure instanceof RequestRejected)) {
    return "The request failed before it reached the backend. Is the server running?";
  }
  const parts = [failure.message];
  if (failure.unresolved.length) parts.push(`Unknown: ${failure.unresolved.join(", ")}`);
  if (failure.unsupported.length) {
    parts.push(`Unsupported: ${failure.unsupported.map((card) => card.name).join(", ")}`);
  }
  return parts.join(" · ");
}
