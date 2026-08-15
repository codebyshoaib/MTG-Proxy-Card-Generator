import { CheckIcon } from "@/components/ui";
import type { Mode } from "@/lib/types";

/**
 * The two modes the client scoped for the MVP. Cards rather than a dropdown because this is the
 * decision that changes what comes back; the reference site's third mode is out of scope.
 */
const MODES: { value: Mode; title: string; blurb: string }[] = [
  {
    value: "CREATIVE_FULL",
    title: "Creative full",
    blurb: "The whole card, painted as one illustration.",
  },
  {
    value: "ART_ONLY",
    title: "Art only",
    blurb: "High-resolution artwork, no frame and no text.",
  },
];

export function ModeSelector({
  value,
  onChange,
}: Readonly<{ value: Mode; onChange: (mode: Mode) => void }>) {
  return (
    <fieldset>
      <legend className="text-sm font-medium">Mode</legend>
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        {MODES.map((mode) => {
          const selected = value === mode.value;
          return (
            <label
              key={mode.value}
              // The radio is visually hidden, so the card has to wear its focus ring — otherwise
              // it is reachable by keyboard with nothing on screen saying so.
              className={`flex cursor-pointer flex-col gap-1 rounded-control border p-3
                transition-colors duration-[--duration-fast]
                has-[:focus-visible]:outline has-[:focus-visible]:outline-2
                has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent-lit
                ${
                  selected
                    ? "border-accent bg-accent/10"
                    : "border-edge bg-raised hover:border-accent"
                }`}
            >
              <input
                type="radio"
                name="mode"
                value={mode.value}
                checked={selected}
                onChange={() => onChange(mode.value)}
                className="sr-only"
              />
              <span className="flex items-center gap-1.5 text-sm font-medium">
                {selected && <CheckIcon className="size-3.5 text-accent-lit" />}
                {mode.title}
              </span>
              <span className="text-xs text-ink-soft">{mode.blurb}</span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
