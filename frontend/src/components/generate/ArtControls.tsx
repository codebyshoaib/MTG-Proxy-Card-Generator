import { Select, Switch, TextArea } from "@/components/ui";
import { toGroups } from "@/lib/api";
import { FREE_TEXT_LIMIT, type Catalogue, type Mode, type Settings } from "@/lib/types";

/** The three catalogues, the two free-text fields and the three switches. */
export function ArtControls({
  catalogue,
  settings,
  onChange,
  mode,
}: Readonly<{
  catalogue: Catalogue | null;
  settings: Settings;
  onChange: (patch: Partial<Settings>) => void;
  mode: Mode;
}>) {
  const composited = mode === "CREATIVE_FULL";

  return (
    <div className="flex flex-col gap-5">
      <Select
        id="art-style"
        label="Art style"
        placeholder="Model's choice"
        value={settings.art_style}
        onChange={(art_style) => onChange({ art_style })}
        groups={toGroups(catalogue?.art_styles)}
      />
      <Select
        id="art-direction"
        label="Art direction"
        placeholder="Model's choice"
        value={settings.art_direction}
        onChange={(art_direction) => onChange({ art_direction })}
        groups={toGroups(catalogue?.art_directions)}
      />
      <Select
        id="color-palette"
        label="Colour palette"
        placeholder="Model's choice"
        value={settings.color_palette}
        onChange={(color_palette) => onChange({ color_palette })}
        groups={toGroups(catalogue?.color_palettes)}
        hint="Applied within the card's own colour identity, never over it."
      />

      <TextArea
        id="custom-style"
        label="Custom art style"
        placeholder="wet chalk on slate"
        hint="Replaces the style above."
        limit={FREE_TEXT_LIMIT}
        value={settings.custom_style}
        onChange={(custom_style) => onChange({ custom_style })}
      />
      <TextArea
        id="custom-notes"
        label="Custom art notes"
        placeholder="a ruined castle behind the subject"
        hint="Added to the brief verbatim."
        limit={FREE_TEXT_LIMIT}
        value={settings.custom_art_notes}
        onChange={(custom_art_notes) => onChange({ custom_art_notes })}
      />

      <div className="flex flex-col gap-2 border-t border-rule pt-4">
        <Switch
          id="reference"
          label="Use the original art as reference"
          description="Sends Scryfall's own artwork so the subject stays recognisable."
          checked={settings.use_original_art_reference}
          onChange={(use_original_art_reference) => onChange({ use_original_art_reference })}
        />
        {/* Both of these describe printed furniture, so neither means anything in Art Only. */}
        <Switch
          id="borderless"
          label="Borderless"
          description="Runs the art to the card's edge instead of growing a border from the scene."
          checked={settings.borderless}
          onChange={(borderless) => onChange({ borderless })}
          disabled={!composited}
        />
        <Switch
          id="flavor"
          label="Include flavour text"
          description="Prints the card's flavour text under its rules."
          checked={settings.include_flavor_text}
          onChange={(include_flavor_text) => onChange({ include_flavor_text })}
          disabled={!composited}
        />
      </div>
    </div>
  );
}
