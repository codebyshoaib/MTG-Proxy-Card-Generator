import { GenerateWorkspace } from "@/components/generate/GenerateWorkspace";
import { SiteHeader } from "@/components/SiteHeader";

/**
 * A Server Component. Only `GenerateWorkspace` ships as a client bundle — marking the whole
 * route `'use client'` would drag the header, the hero and every string into it.
 */
export default function GeneratePage() {
  return (
    <div className="min-h-full">
      <SiteHeader />

      <main className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-10 sm:py-12">
        <div className="max-w-2xl">
          <h1 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">
            Generate your deck
          </h1>
          <p className="mt-3 text-sm text-ink-soft sm:text-base">
            Paste a card list and every card comes back repainted — the artwork alone, or the
            whole card with its rules text printed from Scryfall rather than written by the model.
          </p>
        </div>

        <GenerateWorkspace />
      </main>
    </div>
  );
}
