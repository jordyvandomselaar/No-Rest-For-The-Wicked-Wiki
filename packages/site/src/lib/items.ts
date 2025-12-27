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
  sources?: string[];
  asset_guid?: number;
  recipes_as_input?: ItemRecipe[];
  recipes_as_output?: ItemRecipe[];
  runes?: string[];
  utility_runes?: string[];
  default_runes?: string[];
};

export type ItemsById = Record<string, ItemRecord>;

export function loadItems(): ItemsById {
  const itemsPath = new URL("../../../crawler/out/items.json", import.meta.url);
  const raw = fs.readFileSync(itemsPath, "utf-8");
  return JSON.parse(raw) as ItemsById;
}
