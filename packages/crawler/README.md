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
`qdb*_assets_all_*.bundle`. This is the fastest way to build a wiki item list.

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
