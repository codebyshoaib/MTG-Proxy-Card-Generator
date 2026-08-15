import { CONTROL, Field } from "./Field";

/** A textarea with an optional live character budget. */
export function TextArea({
  id,
  label,
  value,
  onChange,
  placeholder,
  hint,
  rows = 3,
  limit,
  mono,
  required,
}: Readonly<{
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  hint?: React.ReactNode;
  rows?: number;
  limit?: number;
  mono?: boolean;
  required?: boolean;
}>) {
  // Near the ceiling the count stops being decoration and starts being a warning, so it changes
  // colour before the input silently stops accepting keystrokes.
  const nearLimit = limit !== undefined && value.length > limit * 0.9;

  return (
    <Field
      label={label}
      htmlFor={id}
      hint={
        limit === undefined ? (
          hint
        ) : (
          <span className="flex justify-between gap-3">
            <span>{hint}</span>
            <span className={nearLimit ? "text-accent-lit" : undefined}>
              {value.length}/{limit}
            </span>
          </span>
        )
      }
    >
      <textarea
        id={id}
        rows={rows}
        required={required}
        maxLength={limit}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className={`${CONTROL} resize-y ${mono ? "font-mono" : ""}`}
      />
    </Field>
  );
}
