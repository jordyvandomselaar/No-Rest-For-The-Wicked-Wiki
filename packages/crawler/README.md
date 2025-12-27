# Crawler

This package hosts asset crawler and data-mining scripts for the game install.

## Setup

Use mise to install Python, then install the Unity parsing dependency.

```bash
mise install python@3.12
mise exec -- python -m pip install --upgrade pip
mise exec -- python -m pip install UnityPy
```

## Scan for item-like assets

```bash
mise exec -- bun run --cwd packages/crawler scan-items
```

Outputs `packages/crawler/out/items_scan.jsonl` with the bundle name, object type, and asset name.

## Extract item names/descriptions

```bash
mise exec -- bun run --cwd packages/crawler crawl
```

Outputs `packages/crawler/out/items.json` with localization-backed item names/descriptions sourced from
`qdb*_assets_all_*.bundle`. The output is a JSON object keyed by item ID. This also enriches items with
refinery recipes sourced from
`StreamingAssets/quantumDatabase.bin` (e.g., Pine Wood -> Pine Planks).

Refinery links are written to each item as `recipes_as_input` and `recipes_as_output`. This pass
captures input/output item IDs and a best-effort `minutes` value from the QDB blob.

Rune links are captured by scanning item definitions in bundles and attaching `runes` (weapon runes)
and `utility_runes` (player utility runes) arrays of item IDs where found. Each entry also includes
`runes_data` / `utility_runes_data` arrays with `{ id, name, description }` for the linked runes.
Default weapon loadouts discovered in scene bundles are attached as `default_runes` arrays for
weapon items only (`items.gear.weapons.*`).
Default rune scanning uses `static_scenes_all_*.bundle` by default. Use `--no-default-rune-scan` to
skip it for faster iteration, or `--default-rune-bundle-pattern` to override the bundle globs.

## Dump candidate assets

```bash
mise exec -- bun run --cwd packages/crawler dump-assets -- --max-objects 200
```

Outputs `packages/crawler/out/items_dump.jsonl` with typetree data for ScriptableObject/MonoBehaviour
and text payloads for TextAsset entries.

## Useful flags

- `--filter ""` to disable name filtering.
- `--include-types ScriptableObject` to narrow the scan.
- `--max-bundles 1` to iterate quickly while debugging.
- `--qdb-path "/path/to/quantumDatabase.bin"` to override refinery source.
- `--bundle-pattern "qdb_assets_all_*.bundle"` to override which bundles are scanned for item names/descriptions (comma-separated globs supported).
- `--item-bundle-pattern "qdb_assets_all_*.bundle,static_scenes_all_*.bundle"` to override where rune metadata is scanned (comma-separated globs supported; this is the default).
- `--no-rune-scan-subprocess` to scan rune bundles in-process (the default uses subprocesses to keep memory down).
- `--no-default-rune-scan` to skip default rune extraction.
- `--default-rune-bundle-pattern "static_scenes_all_*.bundle"` to override which bundles are scanned for default runes.
  - These defaults avoid scanning the largest bundles (e.g., `world_scenes_all_*.bundle`) to keep memory usage manageable on WSL.

## Finding bundle names after game updates

Bundle filenames can change with game updates. Use the lightweight scanner in
`packages/crawler/src/scan_bundles.py` to discover which bundles contain the
`items.*` prefixes and rune hints you care about. This scanner streams bundle
data and avoids loading full assets, so it is safe to run on large bundles.
You can run it directly with Python or via `bun run --cwd packages/crawler scan-bundles -- ...`.

### 1) List bundle files (names + sizes)

```bash
ls -lh "/mnt/c/Program Files (x86)/Steam/steamapps/common/NoRestForTheWicked/NoRestForTheWicked_Data/StreamingAssets/aa/StandaloneWindows64"/*.bundle
```

### 2) Quick scan for any `items.` strings (fast, low memory)

```bash
python packages/crawler/src/scan_bundles.py \
  --case-insensitive \
  --max-bytes 67108864 \
  --stop-after-found \
  --needles "items."
```

Bundles that report `items.` hits are good candidates for item definitions.

### 3) Scan for specific prefixes (targeted)

Use your known item prefixes to find the most relevant bundles:

```bash
python packages/crawler/src/scan_bundles.py \
  --case-insensitive \
  --max-bytes 67108864 \
  --stop-after-found \
  --needles "items.consumables.,items.cookingIngredients.,items.craftingMaterials.,items.currency.,items.farming.,items.gear.,items.gems.,items.houseItems.,Items.books.,Items.carpets.,Items.instruments.,Items.lights.,Items.lumberStack.,Items.vases.,items.keyItems.,items.projectiles.,items.questItems.,items.readableItems.,items.runes.,items.scrolls.,items.tools.,items.traps.,items.upgradeMaterials."
```

If you prefer a file instead of a long command line, put one needle per line:

```bash
cat > /tmp/item-needles.txt <<'EOF'
items.consumables.
items.cookingIngredients.
items.craftingMaterials.
items.currency.
items.farming.
items.gear.
items.gems.
items.houseItems.
Items.books.
Items.carpets.
Items.instruments.
Items.lights.
Items.lumberStack.
Items.vases.
items.keyItems.
items.projectiles.
items.questItems.
items.readableItems.
items.runes.
items.scrolls.
items.tools.
items.traps.
items.upgradeMaterials.
EOF

python packages/crawler/src/scan_bundles.py \
  --case-insensitive \
  --max-bytes 67108864 \
  --stop-after-found \
  --needles-file /tmp/item-needles.txt
```

### 4) Deep scan a candidate bundle (when the quick scan is inconclusive)

```bash
python packages/crawler/src/scan_bundles.py \
  --case-insensitive \
  --pattern "qdb_assets_all_*.bundle" \
  --max-bytes 0 \
  --needles "items."
```

Use `--max-bytes 0` to scan the full bundle (slower but thorough).

### 5) Use the discovered bundle names in the crawler

Once you know which bundles contain item definitions and rune hints, pass them
into the crawler:

```bash
bun run --cwd packages/crawler crawl -- \
  --bundle-pattern "qdb_assets_all_*.bundle" \
  --item-bundle-pattern "static_scenes_all_*.bundle"
```

Tip: If you only care about items (and not rune metadata), you can omit
`--item-bundle-pattern` and focus on the bundle(s) that contain `items.*`.

## Asset ID Structure

Items in the game have two types of identifiers:

| ID Type | Example | Description |
|---------|---------|-------------|
| **String ID** | `items.gear.weapons.1Handed.wands.nithGate` | Human-readable hierarchical identifier |
| **Numeric ID (GUID)** | `4360494222496306584` | 64-bit integer stored as `asset_guid` |

Both IDs uniquely identify an item. The string ID is used in localization assets (Name/Description),
while the numeric GUID is used in binary data structures for cross-references.

### Where IDs are stored

| Bundle | Contents |
|--------|----------|
| `qdb_assets_all_*.bundle` | Item definitions, localization, icons |
| `static_scenes_all_*.bundle` | Scene prefabs, spawn configurations, default loadouts |
| `world_scenes_all_*.bundle` | World-placed instances |
| `pooled_prefabs_assets_all_*.bundle` | Prefab pool data |
| `quantumDatabase.bin` | Crafting recipes, refinery data |

### Searching for ID usages

Use the streaming search script to find where IDs appear in binary assets:

```bash
python packages/crawler/src/search_ids.py
```

This searches for both string and numeric IDs across all `.bundle` and `.bin` files
using memory-efficient streaming (safe for large bundles).

## Weapon-Rune Relationships

Default runes for weapons are **not stored in item definitions**. Instead, they are
defined in **scene prefab data** within `static_scenes_all_*.bundle` and `world_scenes_all_*.bundle`.

### Binary Structure

When a weapon spawns with default runes, the data structure looks like:

```
Offset  Bytes                      Description
------  -------------------------  -----------
+0      98 15 09 79 64 96 83 3c   Weapon GUID (little-endian int64)
+8      00 00 00 00 02 00 00 00   Metadata (flags, counts)
+16     02 00 00 00 ...           Additional parameters
...
+80     22                         Rune slot marker (offset varies)
+81     59 e5 d5 97 9a 11 1d 18   Rune 1 GUID (little-endian int64)
+89     01 01 00 00 00 00 00 00   Rune 1 flags
+97     f4 99 0f e0 36 47 50 00   Rune 2 GUID (little-endian int64)
+105    01 01 00 00 00 00 00 00   Rune 2 flags
...     ...                        Additional rune GUID/flag pairs (up to 4 slots total)
```

### Key observations

- The `22` byte acts as a **rune slot type marker** (offset varies by weapon)
- Each rune entry is 16 bytes: 8-byte GUID + 8-byte flags
- Weapons can have 1-4 rune entries; empty slots appear as zero GUIDs
- Weapon and rune GUIDs typically appear 81 bytes apart
- Multiple spawn instances define the same weapon-rune pairing

### Example: Nith Gate

The wand "Nith Gate" (`items.gear.weapons.1Handed.wands.nithGate`) spawns with two default runes:

| Rune | String ID | Numeric GUID |
|------|-----------|--------------|
| Plague Column | `items.runes.plagueColumn` | `1737564386904892761` |
| Plague Splatter | `items.runes.plagueSplatter` | `22596299149777396` |

These relationships are found in 16 locations within `static_scenes_all_*.bundle`
and 2 locations in `world_scenes_all_*.bundle`.

### Finding weapon-rune relationships

Use the streaming pair finder to locate weapons with their default runes:

```bash
python packages/crawler/src/find_rune_link_streaming.py
```

This searches for cases where two GUIDs appear within 512 bytes of each other,
which indicates a weapon-rune binding in scene data.
The consistent weapon+rune pairing across occurrences suggests the weapon's
**default loadout** is applied regardless of acquisition source.
