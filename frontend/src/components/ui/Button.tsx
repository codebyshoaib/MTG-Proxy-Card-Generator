import { SpinnerIcon } from "./icons";

const VARIANTS = {
  primary: "bg-accent text-canvas hover:bg-accent-lit",
  quiet: "border border-edge text-ink hover:border-accent hover:text-accent-lit",
  ghost: "text-ink-soft hover:text-ink",
} as const;

// Both sizes keep the 44px touch target; only the horizontal padding changes, so a header button
// reads as secondary without becoming a smaller hit area (skill §2).
const SIZES = {
  md: "px-5",
  sm: "px-3.5 text-[0.8125rem]",
} as const;

/**
 * The one button. `busy` keeps the label and swaps in a spinner beside it — a button that
 * changes its own width mid-click makes the page jump under the cursor.
 */
export function Button({
  variant = "primary",
  size = "md",
  busy,
  children,
  className = "",
  ...props
}: Readonly<
  React.ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: keyof typeof VARIANTS;
    size?: keyof typeof SIZES;
    busy?: boolean;
  }
>) {
  return (
    <button
      {...props}
      aria-busy={busy}
      className={`inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-control
        text-sm font-semibold transition-colors duration-[--duration-base] ease-[--ease-out]
        disabled:cursor-not-allowed disabled:opacity-50
        ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
    >
      {busy && <SpinnerIcon />}
      {children}
    </button>
  );
}
