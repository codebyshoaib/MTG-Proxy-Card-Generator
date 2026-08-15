import { AlertIcon, CheckIcon, CrossIcon } from "./icons";

/**
 * Icon + word + colour, in that order of importance.
 *
 * Colour is the last of the three deliberately: red/green alone fails for the ~8% of men with
 * a colour vision deficiency, and this badge is how someone knows whether a card is shippable.
 */
const TONES = {
  positive: { Icon: CheckIcon, className: "border-sound/50 text-sound" },
  warning: { Icon: AlertIcon, className: "border-accent-lit/50 text-accent-lit" },
  negative: { Icon: CrossIcon, className: "border-fault/50 text-fault" },
} as const;

export function StatusPill({
  tone,
  children,
}: Readonly<{ tone: keyof typeof TONES; children: React.ReactNode }>) {
  const { Icon, className } = TONES[tone];
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${className}`}
    >
      <Icon className="size-3" />
      {children}
    </span>
  );
}
