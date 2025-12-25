Remaining TODOs

1) Decode QDB recipe schema fully
- Reverse engineer the binary layout around `RefineryItemRecipes` to extract input/output quantities.
- Identify how counts are stored (likely packed ints near `Count`/`CraftedQuantity` markers).
- Validate by cross-checking known recipes (e.g., Pine Wood → Pine Planks) in-game.

2) Add non-refinery recipe tables
- Locate QDB tables for crafting, alchemy, cooking, blacksmithing, etc.
- Map each table to item GUIDs and extract input/output quantities + time + station.
- Deduplicate recipes across tables and standardize output format.

3) Enrich item outputs
- Extend `packages/crawler/src/extract_items.py` to attach:
  - `recipes_as_input` / `recipes_as_output` with quantity + time + station.
  - recipe type (`refinery`, `alchemy`, `cooking`, `smithing`, etc).

4) Validation & tooling
- Build a small verification script to check recipe round-trips (input/output IDs resolve).
- Add a quick report to spot missing quantities/time for any recipe rows.

5) Documentation
- Update `packages/crawler/README.md` with new fields and examples once decoding is done.
