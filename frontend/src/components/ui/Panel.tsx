/** A titled surface. The only container in the app that draws a background. */
export function Panel({
  title,
  hint,
  children,
}: Readonly<{ title?: string; hint?: string; children: React.ReactNode }>) {
  return (
    <section className="rounded-panel border border-rule bg-surface p-5 sm:p-6">
      {title && (
        <header className="mb-5">
          <h2 className="font-display text-base font-semibold">{title}</h2>
          {hint && <p className="mt-1 text-sm text-ink-soft">{hint}</p>}
        </header>
      )}
      {children}
    </section>
  );
}
