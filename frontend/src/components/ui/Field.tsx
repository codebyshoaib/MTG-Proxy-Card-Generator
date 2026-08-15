/**
 * Label, control, helper text — in that order, always visible.
 *
 * A placeholder is not a label: it disappears the moment someone types, which is when they most
 * need to know what they are filling in (skill §8).
 */
export function Field({
  label,
  htmlFor,
  hint,
  children,
}: Readonly<{
  label: string;
  htmlFor: string;
  hint?: React.ReactNode;
  children: React.ReactNode;
}>) {
  const hintId = hint ? `${htmlFor}-hint` : undefined;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium">
        {label}
      </label>
      {children}
      {hint && (
        <p id={hintId} className="text-xs text-ink-soft">
          {hint}
        </p>
      )}
    </div>
  );
}

/** Shared control chrome. `edge` rather than `rule`: a control's boundary needs 3:1 (1.4.11). */
export const CONTROL =
  "w-full min-h-11 rounded-control border border-edge bg-raised px-3 py-2 text-sm text-ink " +
  "placeholder:text-ink-soft transition-colors duration-[--duration-fast] hover:border-accent";
