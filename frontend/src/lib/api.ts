import type { Catalogue, GenerateRequest, Job, Mode, Option, Settings } from "./types";

/** A refusal the user can act on: the reason, plus the card names behind it. */
export class RequestRejected extends Error {
  constructor(
    message: string,
    readonly unresolved: string[] = [],
    readonly unsupported: { name: string; layout: string }[] = [],
  ) {
    super(message);
    this.name = "RequestRejected";
  }
}

async function json<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new RequestRejected(
      body.detail ?? `The backend answered ${response.status}.`,
      body.unresolved ?? [],
      body.unsupported ?? [],
    );
  }
  return body as T;
}

export async function getCatalogue(): Promise<Catalogue> {
  return json<Catalogue>(await fetch("/api/options"));
}

export async function startJob(request: GenerateRequest): Promise<Job> {
  return json<Job>(
    await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    }),
  );
}

export async function getJob(id: string): Promise<Job> {
  return json<Job>(await fetch(`/api/jobs/${id}`));
}

export function toRequest(decklist: string, mode: Mode, settings: Settings): GenerateRequest {
  const text = (value: string) => (value.trim() ? value.trim() : null);
  return {
    decklist,
    frame_version: mode,
    art_style: text(settings.art_style),
    art_direction: text(settings.art_direction),
    color_palette: text(settings.color_palette),
    custom_style: text(settings.custom_style),
    custom_art_notes: text(settings.custom_art_notes),
    include_flavor_text: settings.include_flavor_text,
    use_original_art_reference: settings.use_original_art_reference,
    borderless: settings.borderless,
  };
}

/** Options in the order the backend sent them, bucketed into their `<optgroup>` headings. */
export function toGroups(options: Option[] = []) {
  const groups = new Map<string, { value: string; label: string }[]>();
  for (const option of options) {
    const bucket = groups.get(option.group) ?? [];
    bucket.push({ value: option.value, label: option.label });
    groups.set(option.group, bucket);
  }
  return [...groups].map(([label, entries]) => ({ label, options: entries }));
}
