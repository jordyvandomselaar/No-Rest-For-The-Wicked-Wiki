#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from pathlib import Path

import UnityPy


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_GAME_DIR = "/mnt/c/Program Files (x86)/Steam/steamapps/common/NoRestForTheWicked"
DEFAULT_BUNDLES_SUBDIR = "NoRestForTheWicked_Data/StreamingAssets/aa/StandaloneWindows64"
DEFAULT_OUTPUT_DIR = str(SCRIPT_DIR.parent / "out")
DEFAULT_FILTER = r"(item|weapon|armor|potion|ring|amulet|loot|craft|recipe)"


def iter_bundles(bundles_dir: Path):
    for path in sorted(bundles_dir.glob("*.bundle")):
        if path.is_file():
            yield path


def safe_name(obj):
    try:
        data = obj.read()
        name = getattr(data, "name", None)
        if isinstance(name, str) and name:
            return name
    except Exception:
        return None
    return None


def try_read_typetree(obj):
    try:
        return obj.read_typetree()
    except Exception:
        return None


def try_read_textasset(obj):
    try:
        data = obj.read()
        raw = getattr(data, "script", None)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            for enc in ("utf-8", "utf-16", "latin-1"):
                try:
                    return raw.decode(enc)
                except Exception:
                    continue
        return None
    except Exception:
        return None


def dump_object(bundle_name, obj, out_fh, mode):
    obj_type = obj.type.name
    name = safe_name(obj)
    record = {
        "bundle": bundle_name,
        "path_id": obj.path_id,
        "type": obj_type,
        "name": name,
    }

    if mode == "scan":
        out_fh.write(json.dumps(record, ensure_ascii=True) + "\n")
        return

    if obj_type == "TextAsset":
        text = try_read_textasset(obj)
        if text is not None:
            record["text"] = text
    else:
        tree = try_read_typetree(obj)
        if tree is not None:
            record["data"] = tree

    out_fh.write(json.dumps(record, ensure_ascii=True) + "\n")


def crawl(args):
    game_dir = Path(args.game_dir)
    bundles_dir = Path(args.bundles_dir) if args.bundles_dir else game_dir / DEFAULT_BUNDLES_SUBDIR
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not bundles_dir.exists():
        raise SystemExit(f"Bundles directory not found: {bundles_dir}")

    name_filter = re.compile(args.filter, re.IGNORECASE) if args.filter else None
    include_types = set(args.include_types) if args.include_types else None

    out_path = output_dir / ("items_scan.jsonl" if args.mode == "scan" else "items_dump.jsonl")
    written = 0
    scanned = 0

    with out_path.open("w", encoding="utf-8") as out_fh:
        for bundle_path in iter_bundles(bundles_dir):
            if args.max_bundles and scanned >= args.max_bundles:
                break

            scanned += 1
            env = UnityPy.load(str(bundle_path))
            bundle_name = bundle_path.name

            for obj in env.objects:
                obj_type = obj.type.name
                if include_types and obj_type not in include_types:
                    continue

                name = safe_name(obj)
                if name_filter and name:
                    if not name_filter.search(name):
                        continue
                elif name_filter and not name:
                    continue

                dump_object(bundle_name, obj, out_fh, args.mode)
                written += 1
                if args.max_objects and written >= args.max_objects:
                    break

            if args.max_objects and written >= args.max_objects:
                break

    print(f"Wrote {written} records to {out_path}")


def build_parser():
    parser = argparse.ArgumentParser(description="Scan Unity bundles for item-like assets.")
    parser.add_argument("--game-dir", default=DEFAULT_GAME_DIR, help="Game install root.")
    parser.add_argument("--bundles-dir", default="", help="Override bundles directory.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory.")
    parser.add_argument("--mode", choices=["scan", "dump"], default="scan", help="Scan or dump assets.")
    parser.add_argument(
        "--filter",
        default=DEFAULT_FILTER,
        help="Regex applied to asset name for filtering. Use empty string to disable.",
    )
    parser.add_argument(
        "--include-types",
        nargs="*",
        default=["ScriptableObject", "MonoBehaviour", "TextAsset"],
        help="Unity object types to include.",
    )
    parser.add_argument("--max-objects", type=int, default=0, help="Stop after N records (0 = no limit).")
    parser.add_argument("--max-bundles", type=int, default=0, help="Stop after N bundles (0 = no limit).")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.filter == "":
        args.filter = None
    if args.max_objects == 0:
        args.max_objects = None
    if args.max_bundles == 0:
        args.max_bundles = None
    crawl(args)


if __name__ == "__main__":
    main()
