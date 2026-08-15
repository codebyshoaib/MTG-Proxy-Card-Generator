import { Button } from "@/components/ui";

/**
 * The masthead. Static, so it stays a Server Component.
 *
 * Sign in and Get started are placeholders for the Milestone 2 account system and do nothing
 * yet — but they are real `<button>`s rather than `<a href="#">`, so they are keyboard-reachable
 * and announce as controls instead of as links that go nowhere.
 */
export function SiteHeader() {
  return (
    <header className="border-b border-rule">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-3">
        <p className="font-display text-base font-semibold">
          <span className="text-accent">MTG</span> Proxy Generator
        </p>
        <nav aria-label="Account" className="flex items-center gap-2">
          <Button type="button" variant="ghost" size="sm">
            Sign in
          </Button>
          <Button type="button" size="sm">
            Get started
          </Button>
        </nav>
      </div>
    </header>
  );
}
