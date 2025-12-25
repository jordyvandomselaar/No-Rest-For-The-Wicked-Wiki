#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import UnityPy


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_GAME_DIR = "/mnt/c/Program Files (x86)/Steam/steamapps/common/NoRestForTheWicked"
DEFAULT_BUNDLES_SUBDIR = "NoRestForTheWicked_Data/StreamingAssets/aa/StandaloneWindows64"
DEFAULT_OUTPUT_DIR = str(SCRIPT_DIR.parent / "out")


LANG_KEYS = {
    "English",
    "French",
    "Italian",
    "German",
    "Spanish",
    "BrazilianPortuguese",
    "TraditionalChinese",
    "SimplifiedChinese",
    "Korean",
    "Russian",
    "Japanese",
    "Polish",
}


def iter_bundles(bundles_dir: Path, pattern: str):
    for path in sorted(bundles_dir.glob(pattern)):
        if path.is_file():
            yield path


def extract_locales(tree):
    locales = {}
    for key in LANG_KEYS:
        value = tree.get(key)
        if isinstance(value, str) and value:
            locales[key] = value
    return locales


def normalize_id(raw_id: str):
    if raw_id.endswith(".Name"):
        return raw_id[: -len(".Name")]
    if raw_id.endswith(".Description"):
        return raw_id[: -len(".Description")]
    return raw_id


def classify_entry(raw_id: str):
    if raw_id.endswith(".Name"):
        return "name"
    if raw_id.endswith(".Description"):
        return "description"
    return "other"


def crawl(args):
    game_dir = Path(args.game_dir)
    bundles_dir = Path(args.bundles_dir) if args.bundles_dir else game_dir / DEFAULT_BUNDLES_SUBDIR
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not bundles_dir.exists():
        raise SystemExit(f"Bundles directory not found: {bundles_dir}")

    items = {}
    scanned = 0

    for bundle_path in iter_bundles(bundles_dir, args.bundle_pattern):
        env = UnityPy.load(str(bundle_path))
        for obj in env.objects:
            scanned += 1
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                tree = obj.read_typetree()
            except Exception:
                continue

            raw_id = tree.get("Id")
            if not isinstance(raw_id, str):
                continue
            if not raw_id.startswith("items."):
                continue

            entry_kind = classify_entry(raw_id)
            if entry_kind == "other" and not args.include_other:
                continue

            locales = extract_locales(tree)
            if not locales and entry_kind != "other":
                continue

            item_id = normalize_id(raw_id)
            record = items.setdefault(
                item_id,
                {
                    "id": item_id,
                    "name": None,
                    "description": None,
                    "name_locales": {},
                    "description_locales": {},
                    "sources": set(),
                },
            )
            record["sources"].add(bundle_path.name)

            if entry_kind == "name":
                record["name"] = locales.get("English", record["name"])
                record["name_locales"].update(locales)
            elif entry_kind == "description":
                record["description"] = locales.get("English", record["description"])
                record["description_locales"].update(locales)
            else:
                # keep the raw id in sources so we can revisit other metadata later
                record.setdefault("other_ids", []).append(raw_id)

    out_path = output_dir / "items.json"
    cleaned = []
    for item in items.values():
        item["sources"] = sorted(item["sources"])
        if "other_ids" in item:
            item["other_ids"] = sorted(set(item["other_ids"]))
        cleaned.append(item)

    cleaned.sort(key=lambda x: x["id"])
    out_path.write_text(json.dumps(cleaned, ensure_ascii=True, indent=2), encoding="utf-8")
    print(f"Scanned {scanned} objects. Wrote {len(cleaned)} items to {out_path}")


def build_parser():
    parser = argparse.ArgumentParser(description="Extract item names/descriptions from localization assets.")
    parser.add_argument("--game-dir", default=DEFAULT_GAME_DIR, help="Game install root.")
    parser.add_argument("--bundles-dir", default="", help="Override bundles directory.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory.")
    parser.add_argument(
        "--bundle-pattern",
        default="qdb*_assets_all_*.bundle",
        help="Glob pattern for bundles to scan.",
    )
    parser.add_argument(
        "--include-other",
        action="store_true",
        help="Include localization entries that are not Name/Description.",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    crawl(args)


if __name__ == "__main__":
    main()
