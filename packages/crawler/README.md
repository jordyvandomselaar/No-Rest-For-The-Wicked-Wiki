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
`qdb*_assets_all_*.bundle`. This also enriches items with refinery recipes sourced from
`StreamingAssets/quantumDatabase.bin` (e.g., Pine Wood -> Pine Planks).

Refinery links are written to each item as `recipes_as_input` and `recipes_as_output`. This pass
captures input/output item IDs and a best-effort `minutes` value from the QDB blob.

Rune links are captured by scanning item definitions in bundles and attaching `runes` (weapon runes)
and `utility_runes` (player utility runes) arrays of item IDs where found. Each entry also includes
`runes_data` / `utility_runes_data` arrays with `{ id, name, description }` for the linked runes.
Default weapon loadouts discovered in scene bundles are attached as `default_runes` /
`default_runes_data` arrays with the same shape as `runes_data`.

Spawn locations are extracted by default from `static_scenes_all_*.bundle` and `world_scenes_all_*.bundle`.
These indicate where items can be obtained (vendors, loot pools, world spawns). Each item may have a
`spawn_locations` array with entries like:

```json
{
  "bundle": "static_scenes_all_*.bundle",
  "type": "loot_pool",
  "occurrences": 3,
  "offset_range": [8041120, 8078030]
}
```

Use `--no-spawn-scan` to skip spawn location extraction (useful for faster iteration).

## Extract spawn locations (standalone)

```bash
mise exec -- bun run --cwd packages/crawler scan-spawns -- --verbose
```

This scans scene bundles for item GUIDs and outputs `packages/crawler/out/spawn_locations.json`.
Useful for analyzing spawn data without re-running the full crawler.

Options:
- `--item-filter "items.gear.weapons"` to limit to specific item types
- `--bundle-pattern "static_scenes_all_*.bundle"` to scan specific bundles
- `--verbose` to show progress

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
- `--no-spawn-scan` to skip spawn location extraction entirely.
- `--spawn-bundle-pattern "static_scenes_all_*.bundle"` to override which bundles are scanned for spawn locations.
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
+80     22                         Rune slot marker
+81     59 e5 d5 97 9a 11 1d 18   Rune 1 GUID (little-endian int64)
+89     01 01 00 00 00 00 00 00   Rune 1 flags
+97     f4 99 0f e0 36 47 50 00   Rune 2 GUID (little-endian int64)
+105    01 01 00 00 00 00 00 00   Rune 2 flags
```

### Key observations

- The `22` byte acts as a **rune slot type marker**
- Each rune entry is 16 bytes: 8-byte GUID + 8-byte flags
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

### Understanding spawn location data

The weapon-rune pairings found in scene bundles are **not individual world locations**.
Instead, they represent various game systems that can spawn the weapon:

| Data Type | Bundle | Purpose |
|-----------|--------|---------|
| Loot Source Data | `static_scenes_all_*.bundle` | Item pool definitions for the loot system |
| Vendor Inventory | `static_scenes_all_*.bundle` | Items available from merchants |
| Cerim Whispers | `static_scenes_all_*.bundle` | Special reward system items |
| World Instances | `world_scenes_all_*.bundle` | Actual world-placed weapon spawns |

#### Offset grouping analysis

Spawn entries cluster by proximity. Entries within ~50KB of each other typically belong
to the same scene object (loot pool, vendor, etc.). Larger gaps (500KB+) indicate
different scene objects.

Example for Nith Gate (18 total occurrences):

```
Group 1: 3 entries @ 0x7A39A0-0x7B2734  (VendorInventory, LootSourceData)
Group 2: 2 entries @ 0x873F58-0x8785A3  (loot table variant)
Group 3: 2 entries @ 0x907D5B-0x90BED7  (loot table variant)
Group 4: 2 entries @ 0x99A607-0x99EE05  (loot table variant)
Group 5: 1 entry  @ 0x9F2CC2           (CerimWhisperData, VendorInventory)
Group 6: 2 entries @ 0xA6D8DA-0xA72A65  (loot table variant)
Group 7: 2 entries @ 0xB05040-0xB09321  (loot table variant)
Group 8: 2 entries @ 0xB936FA-0xB97DC5  (loot table variant)
---
World:   2 entries @ 0x328AC1A-0x328FDA5 (world_scenes - actual spawns)
```

The 8 groups in `static_scenes` represent ~8 distinct loot pools or vendor inventories.
Multiple entries per group are likely difficulty tiers or drop weight variants.

The consistent weapon+rune pairing across all entries confirms the weapon's
**default loadout** is applied universally regardless of acquisition source.

## Spawn Location Investigation (Incomplete)

Investigation into extracting meaningful spawn location data (vendor names, loot pool names, etc.)
revealed that this data is not easily accessible. This section documents findings for future work.

### What we found

**Item GUID occurrences in `static_scenes_all_*.bundle`:**

When searching for item GUIDs in static_scenes, matches are found in `CinematicReplaySave` objects:
- `theRisenAttackCinematicReplaySave`
- `theBreachCinematicReplaySave`
- `theFallenCityCinematicReplaySave`
- etc.

These are **pre-recorded gameplay sessions** used for in-game cinematics. They contain serialized
player inventory state (`SerializedSaveData` field) - NOT spawn configuration data. The item GUIDs
appear because the replay captured the player's inventory at recording time.

**Item GUID occurrences in `quantumDatabase.bin`:**

| Structure | Description |
|-----------|-------------|
| `ArmamentFilters` (offset ~128M) | Weapon category lists - groups weapons by type (wands, staves, etc.) |
| Near `LootSource` markers | Crafting materials found, but NOT weapons |
| Weapon clusters (12-byte spacing) | Compact weapon ID lists, purpose unknown |

Example context around Nith Gate in quantumDatabase.bin:
```
moltenClutch, moonShard, nithGate, Filter, runeStricken, sanglier, tarnished...
```
This shows Nith Gate in a **filter list** with other wands, not a loot/drop table.

**What's NOT accessible:**

| Data | Location | Issue |
|------|----------|-------|
| Loot tables | `quantumDatabase.bin` | Custom serialization (likely MessagePack), structure not decoded |
| Vendor inventories | Unknown | Not found in parsed Unity objects |
| Drop rates/weights | Unknown | No `Drop`, `Chance`, `Weight`, `Rate` markers near weapon GUIDs |
| World spawn points | `world_scenes_all_*.bundle` | 20GB file, same cinematic replay issue |

### Bundle contents summary

| Bundle | Size | Unity Objects | Item GUIDs Found In |
|--------|------|---------------|---------------------|
| `qdb_assets_all_*.bundle` | 1.7GB | MonoBehaviour (item defs), worldlut | Item definitions, ArmamentViews |
| `qdb_binary_assets_all_*.bundle` | 428MB | TextAsset, Mesh | Not searched |
| `static_scenes_all_*.bundle` | 586MB | 54K MonoBehaviour, 40K GameObject | CinematicReplaySave only |
| `world_scenes_all_*.bundle` | 20GB | Not fully explored | Likely same pattern |
| `pooled_prefabs_assets_all_*.bundle` | 10GB | Not explored | Unknown |
| `quantumDatabase.bin` | 553MB | Binary blob | ArmamentFilters, LootSource (materials only) |

### worldlut structure

The `worldlut` object in `qdb_assets_all_*.bundle` contains:

```
Keys: m_GameObject, m_Enabled, m_Script, m_Name, AssetGuid, Assets, ChunkAssets,
      UnityPayloads, ArmamentViews, ArmamentViewsFilters, HeroItemSortingOrder,
      PooledPrefabs, DebugNames, CharacterMap, PrefabDependencyGraph

ArmamentViews: 210 entries (weapon view/animation configs)
PooledPrefabs: 4915 entries (prefab references, empty Configuration dicts)
```

`ArmamentViews[144]` contains Nith Gate's weapon view config:
```python
{
  'Data': ...,
  'Filter': ...,
  'ParentViewFilterIndex': ...,
  'WwiseConfig': ...,
  'AnimationSet': ...,
  'ViewPrefabs': ...,
  'Weapon': {'Id': {'Value': 4360494222496306584}}  # Nith Gate GUID
}
```

This is **animation/view configuration**, not spawn data.

### Scripts created

| Script | Purpose | Status |
|--------|---------|--------|
| `extract_spawn_locations.py` | Parallel GUID search in bundles | Works, but data not useful |
| `find_rune_link_streaming.py` | Find weapon-rune pairs | Works |
| `find_nearby_runes.py` | Find all runes near a weapon | Works |
| `search_ids.py` | Search for specific IDs | Works |

### Future investigation paths

1. **Decode quantumDatabase.bin format** - Likely MessagePack with custom schema. The `LootSource`
   markers (630 occurrences) suggest loot table data exists but in an unparsed structure.

2. **Explore pooled_prefabs_assets** - 10GB bundle with 4915 prefab references. May contain
   actual spawn/drop configurations.

3. **Game memory analysis** - Runtime inspection might reveal how loot tables are loaded/used.

4. **Community resources** - Check if modding communities have decoded these formats.

### Current spawn_locations output

The `spawn_locations` field in items.json currently shows:
- Bundle name where GUID was found
- Number of occurrences
- Offset ranges
- Type: "unknown" (context detection failed)

This data is of **limited utility** since it's detecting cinematic replay inventory snapshots,
not actual spawn configurations. Consider disabling with `--no-spawn-scan`.
