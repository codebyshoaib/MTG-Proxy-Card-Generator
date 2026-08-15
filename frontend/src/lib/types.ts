/**
 * The backend's shapes.
 *
 * Field names are the reference site's own `POST /api/ai-proxies/generate/` payload, which our
 * Django layer accepts verbatim — so nothing anywhere translates anything.
 */

export type Option = { value: string; label: string; group: string };

export type Catalogue = {
  modes: string[];
  art_styles: Option[];
  art_directions: Option[];
  color_palettes: Option[];
};

export type Mode = "ART_ONLY" | "CREATIVE_FULL";

export type CardResult = {
  name: string;
  quantity: number;
  status: "ok" | "unsound" | "failed";
  image: string | null;
  problems: { code: string; detail: string }[];
  log: string[];
  seconds?: number;
};

export type Job = {
  id: string;
  mode: Mode;
  status: "queued" | "running" | "done" | "failed";
  error: string;
  cards: { name: string; quantity: number }[];
  faces: number;
  workers: number;
  /** Seconds left, or null once there is nothing left to wait for. */
  eta_seconds: number | null;
  unresolved: string[];
  unsupported: { name: string; layout: string }[];
  results: CardResult[];
};

export type GenerateRequest = {
  decklist: string;
  frame_version: Mode;
  art_style: string | null;
  art_direction: string | null;
  color_palette: string | null;
  custom_style: string | null;
  custom_art_notes: string | null;
  include_flavor_text: boolean;
  use_original_art_reference: boolean;
  borderless: boolean;
};

/** Everything the options panel edits, so a block takes one prop instead of ten. */
export type Settings = {
  art_style: string;
  art_direction: string;
  color_palette: string;
  custom_style: string;
  custom_art_notes: string;
  include_flavor_text: boolean;
  use_original_art_reference: boolean;
  borderless: boolean;
};

/** The reference site's own defaults, read off its bundle — except `borderless`, which the
 *  client asked for on 2026-08-13. */
export const DEFAULT_SETTINGS: Settings = {
  art_style: "fantasy_realistic",
  art_direction: "dynamic",
  color_palette: "vibrant",
  custom_style: "",
  custom_art_notes: "",
  include_flavor_text: false,
  use_original_art_reference: true,
  borderless: true,
};

export const FREE_TEXT_LIMIT = 500;
