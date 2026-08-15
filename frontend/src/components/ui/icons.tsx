/**
 * The icon set, drawn inline.
 *
 * SVG rather than emoji, because an emoji is a font-dependent glyph that a screen reader
 * announces as prose. Inline rather than a library, because six 24px paths do not earn a
 * dependency. Every icon is decorative — the label beside it carries the meaning — so they all
 * ship `aria-hidden`.
 */

type IconProps = Readonly<{ className?: string }>;

function Icon({ children, className = "size-4" }: Readonly<{ children: React.ReactNode; className?: string }>) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      {children}
    </svg>
  );
}

export const CheckIcon = ({ className }: IconProps) => (
  <Icon className={className}>
    <path d="m5 13 4 4L19 7" />
  </Icon>
);

export const AlertIcon = ({ className }: IconProps) => (
  <Icon className={className}>
    <path d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
  </Icon>
);

export const CrossIcon = ({ className }: IconProps) => (
  <Icon className={className}>
    <path d="M18 6 6 18M6 6l12 12" />
  </Icon>
);

export const ChevronIcon = ({ className }: IconProps) => (
  <Icon className={className}>
    <path d="m6 9 6 6 6-6" />
  </Icon>
);

export const DownloadIcon = ({ className }: IconProps) => (
  <Icon className={className}>
    <path d="M12 3v12m0 0 4-4m-4 4-4-4M3 17v2a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-2" />
  </Icon>
);

export const SpinnerIcon = ({ className = "size-4" }: IconProps) => (
  <svg aria-hidden viewBox="0 0 24 24" fill="none" className={`${className} animate-spin`}>
    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth={2} opacity={0.25} />
    <path
      d="M21 12a9 9 0 0 0-9-9"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
    />
  </svg>
);
