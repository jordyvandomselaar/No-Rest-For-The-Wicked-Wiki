#!/usr/bin/env python3
import argparse
import gc
import json
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import UnityPy


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_GAME_DIR = "/mnt/c/Program Files (x86)/Steam/steamapps/common/NoRestForTheWicked"
DEFAULT_BUNDLES_SUBDIR = "NoRestForTheWicked_Data/StreamingAssets/aa/StandaloneWindows64"
DEFAULT_QDB_SUBPATH = "NoRestForTheWicked_Data/StreamingAssets/quantumDatabase.bin"
DEFAULT_OUTPUT_DIR = str(SCRIPT_DIR.parent / "out")
DEFAULT_ITEM_BUNDLE_PATTERN = "items*_assets_all_*.bundle"


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


def try_read_typetree(obj):
    try:
        return obj.read_typetree()
    except Exception:
        return None


def extract_english_and_has_locale(tree):
    english = None
    has_locale = False
    for key in LANG_KEYS:
        value = tree.get(key)
        if isinstance(value, str) and value:
            has_locale = True
            if key == "English":
                english = value
    return english, has_locale


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


def classify_rune_bucket(key_path):
    if not key_path:
        return "runes"
    lowered = " ".join(key_path).lower()
    if "utility" in lowered:
        return "utility_runes"
    if "rune" in lowered:
        return "runes"
    return "runes"


def collect_rune_refs(tree, rune_path_ids, rune_guid_to_id):
    runes = []
    utility_runes = []
    seen = set()
    seen_utility = set()

    def add_rune(bucket, rune_id):
        if bucket == "utility_runes":
            if rune_id in seen_utility:
                return
            seen_utility.add(rune_id)
            utility_runes.append(rune_id)
            return
        if rune_id in seen:
            return
        seen.add(rune_id)
        runes.append(rune_id)

    stack = [(tree, ())]
    while stack:
        node, key_path = stack.pop()
        if isinstance(node, dict):
            if "m_PathID" in node and "m_FileID" in node:
                path_id = node.get("m_PathID")
                if isinstance(path_id, int) and path_id in rune_path_ids:
                    bucket = classify_rune_bucket(key_path)
                    add_rune(bucket, rune_path_ids[path_id])
            for key, value in node.items():
                stack.append((value, key_path + (str(key),)))
            continue

        if isinstance(node, list):
            for value in node:
                stack.append((value, key_path))
            continue

        if isinstance(node, str):
            if node.startswith("items.runes."):
                bucket = classify_rune_bucket(key_path)
                add_rune(bucket, node)
            continue

        if isinstance(node, int):
            if rune_guid_to_id and any("guid" in key.lower() for key in key_path):
                rune_id = rune_guid_to_id.get(node)
                if rune_id:
                    bucket = classify_rune_bucket(key_path)
                    add_rune(bucket, rune_id)
            continue

    return runes, utility_runes


def merge_rune_results(target, incoming):
    for item_id, runes in incoming.items():
        entry = target.setdefault(item_id, {"runes": [], "utility_runes": []})
        for rune_id in runes.get("runes", []):
            if rune_id not in entry["runes"]:
                entry["runes"].append(rune_id)
        for rune_id in runes.get("utility_runes", []):
            if rune_id not in entry["utility_runes"]:
                entry["utility_runes"].append(rune_id)


def scan_bundle_runes(bundle_path: Path, rune_guid_to_id):
    runes_by_item = {}

    env = UnityPy.load(str(bundle_path))
    item_ids_by_path = {}

    # Pass 1: map item path IDs to item IDs (minimal retention to reduce memory).
    for obj in env.objects:
        if obj.type.name not in {"MonoBehaviour", "ScriptableObject"}:
            continue
        tree = try_read_typetree(obj)
        if not isinstance(tree, dict):
            continue
        raw_id = tree.get("Id")
        if not isinstance(raw_id, str):
            continue
        if not raw_id.startswith("items."):
            continue
        item_id = normalize_id(raw_id)
        item_ids_by_path[obj.path_id] = item_id

    if not item_ids_by_path:
        env = None
        gc.collect()
        return runes_by_item

    rune_path_ids = {
        path_id: item_id
        for path_id, item_id in item_ids_by_path.items()
        if item_id.startswith("items.runes.")
    }

    if not rune_path_ids and not rune_guid_to_id:
        env = None
        gc.collect()
        return runes_by_item

    # Pass 2: rescan only item objects to find rune references.
    for obj in env.objects:
        item_id = item_ids_by_path.get(obj.path_id)
        if not item_id:
            continue
        if item_id.startswith("items.runes."):
            continue
        tree = try_read_typetree(obj)
        if not isinstance(tree, dict):
            continue

        runes, utility_runes = collect_rune_refs(tree, rune_path_ids, rune_guid_to_id)
        if not runes and not utility_runes:
            continue

        entry = runes_by_item.setdefault(item_id, {"runes": [], "utility_runes": []})
        for rune_id in runes:
            if rune_id not in entry["runes"]:
                entry["runes"].append(rune_id)
        for rune_id in utility_runes:
            if rune_id not in entry["utility_runes"]:
                entry["utility_runes"].append(rune_id)

    env = None
    gc.collect()

    return runes_by_item


def extract_item_runes(bundles_dir: Path, pattern: str, rune_guid_to_id, use_subprocess: bool):
    runes_by_item = {}

    if not use_subprocess:
        for bundle_path in iter_bundles(bundles_dir, pattern):
            merge_rune_results(runes_by_item, scan_bundle_runes(bundle_path, rune_guid_to_id))
        return runes_by_item

    rune_guid_pairs = sorted(rune_guid_to_id.items())
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as mapping_fh:
        json.dump(rune_guid_pairs, mapping_fh, ensure_ascii=True)
        mapping_path = mapping_fh.name

    try:
        for bundle_path in iter_bundles(bundles_dir, pattern):
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as out_fh:
                out_path = out_fh.name
            try:
                cmd = [
                    sys.executable,
                    os.fspath(Path(__file__).resolve()),
                    "--scan-runes-bundle",
                    os.fspath(bundle_path),
                    "--rune-guid-map",
                    mapping_path,
                    "--rune-scan-output",
                    out_path,
                ]
                proc = subprocess.run(cmd, text=True, capture_output=True)
                if proc.returncode != 0:
                    raise SystemExit(
                        "Rune scan subprocess failed for "
                        f"{bundle_path.name}:\n{proc.stderr.strip() or proc.stdout.strip()}"
                    )
                with open(out_path, "r", encoding="utf-8") as fh:
                    payload = json.load(fh)
                if payload:
                    merge_rune_results(runes_by_item, payload)
            finally:
                if os.path.exists(out_path):
                    os.unlink(out_path)
    finally:
        if os.path.exists(mapping_path):
            os.unlink(mapping_path)

    return runes_by_item


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

            english, has_locale = extract_english_and_has_locale(tree)
            if not has_locale and entry_kind != "other":
                continue

            item_id = normalize_id(raw_id)
            record = items.setdefault(
                item_id,
                {
                    "id": item_id,
                    "name": None,
                    "description": None,
                    "sources": set(),
                },
            )
            record["sources"].add(bundle_path.name)

            if entry_kind == "name":
                if english:
                    record["name"] = english
                record["name_path_id"] = obj.path_id
            elif entry_kind == "description":
                if english:
                    record["description"] = english
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

    item_bundle_pattern = args.item_bundle_pattern or args.bundle_pattern
    rune_guid_to_id = {
        item["asset_guid"]: item["id"]
        for item in items.values()
        if item.get("asset_guid") is not None and item["id"].startswith("items.runes.")
    }
    rune_details = {
        item["id"]: {
            "id": item["id"],
            "name": item.get("name"),
            "description": item.get("description"),
        }
        for item in items.values()
        if item["id"].startswith("items.runes.")
    }

    def rune_detail_for(rune_id):
        detail = rune_details.get(rune_id)
        if detail:
            return dict(detail)
        return {"id": rune_id, "name": None, "description": None}

    runes_by_item = extract_item_runes(
        bundles_dir,
        item_bundle_pattern,
        rune_guid_to_id,
        args.rune_scan_subprocess,
    )
    for item_id, runes in runes_by_item.items():
        item = items.get(item_id)
        if not item:
            continue
        if runes.get("runes"):
            item["runes"] = runes["runes"]
            item["runes_data"] = [rune_detail_for(rune_id) for rune_id in runes["runes"]]
        if runes.get("utility_runes"):
            item["utility_runes"] = runes["utility_runes"]
            item["utility_runes_data"] = [
                rune_detail_for(rune_id) for rune_id in runes["utility_runes"]
            ]

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
        "--item-bundle-pattern",
        default=DEFAULT_ITEM_BUNDLE_PATTERN,
        help="Glob pattern for bundles to scan for rune metadata.",
    )
    parser.add_argument(
        "--rune-scan-subprocess",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Scan rune bundles in a fresh subprocess per bundle to reduce memory.",
    )
    parser.add_argument(
        "--include-other",
        action="store_true",
        help="Include localization entries that are not Name/Description.",
    )
    parser.add_argument("--scan-runes-bundle", default="", help=argparse.SUPPRESS)
    parser.add_argument("--rune-guid-map", default="", help=argparse.SUPPRESS)
    parser.add_argument("--rune-scan-output", default="", help=argparse.SUPPRESS)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.scan_runes_bundle:
        if not args.rune_guid_map or not args.rune_scan_output:
            raise SystemExit("--scan-runes-bundle requires --rune-guid-map and --rune-scan-output")
        with open(args.rune_guid_map, "r", encoding="utf-8") as fh:
            rune_guid_pairs = json.load(fh)
        rune_guid_to_id = {int(guid): item_id for guid, item_id in rune_guid_pairs}
        result = scan_bundle_runes(Path(args.scan_runes_bundle), rune_guid_to_id)
        Path(args.rune_scan_output).write_text(
            json.dumps(result, ensure_ascii=True),
            encoding="utf-8",
        )
        return
    crawl(args)


if __name__ == "__main__":
    main()
