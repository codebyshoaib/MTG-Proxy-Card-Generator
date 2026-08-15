import { Button, Disclosure, Panel, TextArea } from "@/components/ui";
import type { Catalogue, Mode, Settings } from "@/lib/types";
import { ArtControls } from "./ArtControls";
import { ModeSelector } from "./ModeSelector";

/** Everything that goes into a job. Presentation only — the state lives in the workspace. */
export function GenerateForm({
  catalogue,
  decklist,
  onDecklistChange,
  mode,
  onModeChange,
  settings,
  onSettingsChange,
  onSubmit,
  submitting,
  running,
  error,
}: Readonly<{
  catalogue: Catalogue | null;
  decklist: string;
  onDecklistChange: (value: string) => void;
  mode: Mode;
  onModeChange: (mode: Mode) => void;
  settings: Settings;
  onSettingsChange: (patch: Partial<Settings>) => void;
  onSubmit: () => void;
  submitting: boolean;
  running: boolean;
  error: string | null;
}>) {
  const count = countCards(decklist);

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <Panel title="Deck input" hint="One card per line, with an optional quantity.">
        <div className="flex flex-col gap-5">
          <TextArea
            id="decklist"
            label="Card list"
            required
            mono
            rows={7}
            value={decklist}
            onChange={onDecklistChange}
            placeholder={"1 Terror of the Peaks\n4 Lightning Bolt"}
            hint={
              <>
                Format <code className="text-ink">quantity cardname</code>. A bare name works
                too.
              </>
            }
          />

          <ModeSelector value={mode} onChange={onModeChange} />

          <Disclosure summary="Art options" aside={summarise(settings)}>
            <ArtControls
              catalogue={catalogue}
              settings={settings}
              onChange={onSettingsChange}
              mode={mode}
            />
          </Disclosure>
        </div>
      </Panel>

      <Button type="submit" disabled={submitting || running} busy={submitting || running}>
        {running ? "Generating…" : label(count)}
      </Button>

      {/* The error sits with the control that caused it, not at the top of the page. */}
      {error && (
        <p
          role="alert"
          className="rounded-control border border-fault/50 bg-fault/10 p-3 text-sm"
        >
          {error}
        </p>
      )}
    </form>
  );
}

/** Lines that look like cards, so the button can say what it is about to spend. */
function countCards(decklist: string) {
  return decklist
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#") && !line.startsWith("//")).length;
}

function label(count: number) {
  if (count === 0) return "Generate";
  return count === 1 ? "Generate 1 card" : `Generate ${count} cards`;
}

/** What the folded panel is currently set to, so tuning is visible without opening it. */
function summarise(settings: Settings) {
  const chosen = [settings.custom_style || settings.art_style, settings.art_direction, settings.color_palette]
    .filter(Boolean)
    .map(pretty);
  return chosen.length ? chosen.join(" · ") : "Model's choice";
}

function pretty(value: string) {
  return value.length > 18 ? `${value.slice(0, 18)}…` : value.replaceAll("_", " ");
}
