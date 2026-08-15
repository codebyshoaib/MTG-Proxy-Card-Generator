import { ChevronIcon } from "./icons";
import { CONTROL, Field } from "./Field";

export type SelectGroup = { label: string; options: { value: string; label: string }[] };

/**
 * A native select with grouped options.
 *
 * Native on purpose: it is keyboard- and screen-reader-correct for free, it uses the platform
 * picker on touch, and 48 options in a custom listbox is a scroll-trapping accessibility bug
 * waiting to happen.
 */
export function Select({
  id,
  label,
  value,
  onChange,
  groups,
  placeholder,
  hint,
}: Readonly<{
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  groups: SelectGroup[];
  placeholder: string;
  hint?: string;
}>) {
  return (
    <Field label={label} htmlFor={id} hint={hint}>
      <div className="relative">
        <select
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className={`${CONTROL} cursor-pointer appearance-none pr-10`}
        >
          <option value="">{placeholder}</option>
          {groups.map((group) => (
            <optgroup key={group.label} label={group.label}>
              {group.options.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
        <ChevronIcon className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-ink-soft" />
      </div>
    </Field>
  );
}
