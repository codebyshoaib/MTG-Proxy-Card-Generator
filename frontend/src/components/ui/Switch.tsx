/**
 * A labelled checkbox with its consequence spelled out underneath.
 *
 * The whole row is the hit area, which clears the 44px minimum without a 44px checkbox.
 */
export function Switch({
  id,
  label,
  description,
  checked,
  onChange,
  disabled,
}: Readonly<{
  id: string;
  label: string;
  description: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}>) {
  return (
    <label
      htmlFor={id}
      className={`flex min-h-11 gap-3 rounded-control py-1 transition-colors duration-[--duration-fast]
        ${disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer"}`}
    >
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        aria-describedby={`${id}-description`}
        className="mt-0.5 size-4 shrink-0 cursor-pointer accent-accent disabled:cursor-not-allowed"
      />
      <span className="flex flex-col gap-0.5">
        <span className="text-sm font-medium">{label}</span>
        <span id={`${id}-description`} className="text-xs text-ink-soft">
          {description}
        </span>
      </span>
    </label>
  );
}
