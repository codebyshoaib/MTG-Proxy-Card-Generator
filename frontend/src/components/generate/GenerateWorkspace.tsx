"use client";

import { useCallback, useState } from "react";

import { useCatalogue } from "@/hooks/use-catalogue";
import { useGenerationJob } from "@/hooks/use-generation-job";
import { toRequest } from "@/lib/api";
import { DEFAULT_SETTINGS, type Mode, type Settings } from "@/lib/types";
import { GenerateForm } from "./GenerateForm";
import { ResultsPanel } from "./ResultsPanel";

/**
 * The client island: all of the page's state, and none of its chrome.
 *
 * Everything static — header, hero, footer — stays a Server Component in `app/page.tsx`, so the
 * interactive part is a leaf rather than the whole route.
 */
export function GenerateWorkspace() {
  const { catalogue, error: catalogueError } = useCatalogue();
  const { job, error, submitting, running, start } = useGenerationJob();

  const [decklist, setDecklist] = useState("");
  const [mode, setMode] = useState<Mode>("CREATIVE_FULL");
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);

  const patch = useCallback(
    (change: Partial<Settings>) => setSettings((current) => ({ ...current, ...change })),
    [],
  );

  return (
    <div className="grid items-start gap-8 lg:grid-cols-[27rem_1fr]">
      <GenerateForm
        catalogue={catalogue}
        decklist={decklist}
        onDecklistChange={setDecklist}
        mode={mode}
        onModeChange={setMode}
        settings={settings}
        onSettingsChange={patch}
        onSubmit={() => start(toRequest(decklist, mode, settings))}
        submitting={submitting}
        running={running}
        error={error ?? catalogueError}
      />
      <div aria-live="polite">
        <ResultsPanel job={job} />
      </div>
    </div>
  );
}
