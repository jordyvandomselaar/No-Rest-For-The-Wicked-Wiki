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
mise exec -- npm run crawl -w @nrftw/crawler -- --mode scan
```

Outputs `packages/crawler/out/items_scan.jsonl` with the bundle name, object type, and asset name.

## Extract item names/descriptions

```bash
mise exec -- npm run items -w @nrftw/crawler
```

Outputs `packages/crawler/out/items.json` with localization-backed item names/descriptions sourced from
`qdb*_assets_all_*.bundle`. This also enriches items with refinery recipes sourced from
`StreamingAssets/quantumDatabase.bin` (e.g., Pine Wood -> Pine Planks).

Refinery links are written to each item as `recipes_as_input` and `recipes_as_output`. This pass
captures input/output item IDs and a best-effort `minutes` value from the QDB blob.

Rune links are captured by scanning item definitions in bundles and attaching `runes` (weapon runes)
and `utility_runes` (player utility runes) arrays of item IDs where found. Each entry also includes
`runes_data` / `utility_runes_data` arrays with `{ id, name, description }` for the linked runes.

## Dump candidate assets

```bash
mise exec -- npm run crawl -w @nrftw/crawler -- --mode dump --max-objects 200
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

## Finding bundle names after game updates

Bundle filenames can change with game updates. Use the lightweight scanner in
`packages/crawler/src/scan_bundles.py` to discover which bundles contain the
`items.*` prefixes and rune hints you care about. This scanner streams bundle
data and avoids loading full assets, so it is safe to run on large bundles.
You can run it directly with Python or via `npm run scan-bundles -w @nrftw/crawler -- ...`.

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
npm run items -w @nrftw/crawler -- \
  --bundle-pattern "qdb_assets_all_*.bundle" \
  --item-bundle-pattern "static_scenes_all_*.bundle"
```

Tip: If you only care about items (and not rune metadata), you can omit
`--item-bundle-pattern` and focus on the bundle(s) that contain `items.*`.
