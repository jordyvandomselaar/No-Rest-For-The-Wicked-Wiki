#!/usr/bin/env python3
import argparse
import json
import struct
from pathlib import Path

import UnityPy


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_GAME_DIR = "/mnt/c/Program Files (x86)/Steam/steamapps/common/NoRestForTheWicked"
DEFAULT_BUNDLES_SUBDIR = "NoRestForTheWicked_Data/StreamingAssets/aa/StandaloneWindows64"
DEFAULT_QDB_SUBPATH = "NoRestForTheWicked_Data/StreamingAssets/quantumDatabase.bin"
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
    qdb_path = Path(args.qdb_path) if args.qdb_path else game_dir / DEFAULT_QDB_SUBPATH
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not bundles_dir.exists():
        raise SystemExit(f"Bundles directory not found: {bundles_dir}")

    items = {}
    name_path_to_asset_guid = {}
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

            asset_guid = None
            asset_guid_node = tree.get("AssetGuid")
            if isinstance(asset_guid_node, dict):
                asset_guid = asset_guid_node.get("Value")
            item_name_msg = tree.get("ItemNameMsg")
            if asset_guid is not None and isinstance(item_name_msg, dict):
                path_id = item_name_msg.get("m_PathID")
                if isinstance(path_id, int):
                    name_path_to_asset_guid[path_id] = asset_guid

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
                record["name_path_id"] = obj.path_id
            elif entry_kind == "description":
                record["description"] = locales.get("English", record["description"])
                record["description_locales"].update(locales)
            else:
                # keep the raw id in sources so we can revisit other metadata later
                record.setdefault("other_ids", []).append(raw_id)

    # attach asset guid mapping based on ItemNameMsg path ids
    for item in items.values():
        path_id = item.get("name_path_id")
        if isinstance(path_id, int) and path_id in name_path_to_asset_guid:
            item["asset_guid"] = name_path_to_asset_guid[path_id]

    if qdb_path.exists():
        recipes = extract_refinery_recipes(qdb_path)
        attach_refinery_recipes(items, recipes)

    out_path = output_dir / "items.json"
    cleaned = []
    for item in items.values():
        item["sources"] = sorted(item["sources"])
        if "other_ids" in item:
            item["other_ids"] = sorted(set(item["other_ids"]))
        item.pop("name_path_id", None)
        cleaned.append(item)

    cleaned.sort(key=lambda x: x["id"])
    out_path.write_text(json.dumps(cleaned, ensure_ascii=True, indent=2), encoding="utf-8")
    print(f"Scanned {scanned} objects. Wrote {len(cleaned)} items to {out_path}")


def extract_refinery_recipes(qdb_path: Path):
    needle = b"RefineryItemRecipes"
    recipes = []

    with qdb_path.open("rb") as f:
        data = f.read()

    idx = data.find(needle)
    while idx != -1:
        window = data[idx + len(needle) : idx + len(needle) + 512]
        in_idx = window.find(b"Input")
        out_idx = window.find(b"Out")
        if in_idx != -1 and out_idx != -1:
            input_guid = None
            output_guid = None
            minutes = None

            # Input guid appears after a 0xcf marker (msgpack uint64)
            sub = window[in_idx + 5 :]
            cf_idx = sub.find(b"\xcf")
            if cf_idx != -1 and cf_idx + 9 <= len(sub):
                input_guid = struct.unpack(">Q", sub[cf_idx + 1 : cf_idx + 9])[0]

            # Output guid appears after marker 0xf2 0x03 (observed in refinery table)
            sub2 = window[out_idx + 3 :]
            marker = sub2.find(b"\xf2\x03")
            if marker != -1 and marker + 2 + 8 <= len(sub2):
                output_guid = struct.unpack(">Q", sub2[marker + 2 : marker + 10])[0]

            if input_guid and output_guid:
                minutes_idx = window.find(b"MinutesTo")
                if minutes_idx != -1:
                    base = minutes_idx + len(b"MinutesTo")
                    for off in range(0, 24):
                        if base + off + 4 > len(window):
                            break
                        value = struct.unpack(">f", window[base + off : base + off + 4])[0]
                        if 0.01 <= value <= 120:
                            minutes = round(value, 4)
                            break
                recipes.append(
                    {
                        "input_guid": input_guid,
                        "output_guid": output_guid,
                        "minutes": minutes,
                    }
                )

        idx = data.find(needle, idx + 1)

    return recipes


def attach_refinery_recipes(items, recipes):
    guid_to_item = {}
    for item in items.values():
        guid = item.get("asset_guid")
        if isinstance(guid, int):
            guid_to_item[guid] = item

    seen_pairs = set()
    for recipe in recipes:
        pair = (recipe["input_guid"], recipe["output_guid"])
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        input_item = guid_to_item.get(pair[0])
        output_item = guid_to_item.get(pair[1])
        if not input_item or not output_item:
            continue

        input_item.setdefault("recipes_as_input", []).append(
            {
                "type": "refinery",
                "output": output_item["id"],
                "minutes": recipe.get("minutes"),
            }
        )
        output_item.setdefault("recipes_as_output", []).append(
            {
                "type": "refinery",
                "input": input_item["id"],
                "minutes": recipe.get("minutes"),
            }
        )


def build_parser():
    parser = argparse.ArgumentParser(description="Extract item names/descriptions from localization assets.")
    parser.add_argument("--game-dir", default=DEFAULT_GAME_DIR, help="Game install root.")
    parser.add_argument("--bundles-dir", default="", help="Override bundles directory.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory.")
    parser.add_argument("--qdb-path", default="", help="Override quantumDatabase.bin path.")
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
