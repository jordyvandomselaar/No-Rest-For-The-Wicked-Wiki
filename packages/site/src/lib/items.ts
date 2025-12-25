import fs from "node:fs";

export type ItemRecipe = {
  type: string;
  input?: string;
  output?: string;
  minutes?: number | null;
};

export type ItemRecord = {
  id: string;
  name?: string | null;
  description?: string | null;
  name_locales?: Record<string, string>;
  description_locales?: Record<string, string>;
  sources?: string[];
  asset_guid?: number;
  recipes_as_input?: ItemRecipe[];
  recipes_as_output?: ItemRecipe[];
};

export function loadItems(): ItemRecord[] {
  const itemsPath = new URL("../../../crawler/out/items.json", import.meta.url);
  const raw = fs.readFileSync(itemsPath, "utf-8");
  return JSON.parse(raw) as ItemRecord[];
}
