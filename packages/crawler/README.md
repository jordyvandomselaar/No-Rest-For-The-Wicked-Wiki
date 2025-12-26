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
- `--item-bundle-pattern "items*_assets_all_*.bundle"` to override where rune metadata is scanned (this is the default).
