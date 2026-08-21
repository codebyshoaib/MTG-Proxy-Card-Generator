"use client";

import { useEffect, useState } from "react";

import { getCatalogue } from "@/lib/api";
import type { Catalogue } from "@/lib/types";

/** The 48/21/20 catalogue, fetched once. The backend owns it; nothing here holds a copy. */
export function useCatalogue() {
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getCatalogue()
      .then((loaded) => live && setCatalogue(loaded))
      .catch((failure: unknown) => {
        if (!live) return;
        const detail =
          failure instanceof Error && failure.message
            ? failure.message
            : "Could not load the style catalogue from the backend.";
        setError(detail);
      });
    return () => {
      live = false;
    };
  }, []);

  return { catalogue, error };
}
