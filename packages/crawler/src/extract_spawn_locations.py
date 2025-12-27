#!/usr/bin/env python3
"""
Memory-efficient streaming extraction of spawn location data from scene bundles.

Scans static_scenes_all_*.bundle and world_scenes_all_*.bundle for item GUIDs
and extracts context to identify spawn sources (vendors, loot pools, etc.).
"""

import argparse
import json
import mmap
import os
import struct
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_GAME_DIR = "/mnt/c/Program Files (x86)/Steam/steamapps/common/NoRestForTheWicked"
DEFAULT_BUNDLES_SUBDIR = "NoRestForTheWicked_Data/StreamingAssets/aa/StandaloneWindows64"
DEFAULT_OUTPUT_DIR = str(SCRIPT_DIR.parent / "out")

CHUNK_SIZE = 256 * 1024 * 1024  # 256MB chunks for speed
CONTEXT_WINDOW = 512  # Bytes around GUID to extract for context
PROXIMITY_THRESHOLD = 50 * 1024  # 50KB - entries within this distance are grouped
MAX_WORKERS = min(8, os.cpu_count() or 4)  # Use up to 8 cores


# Keywords that identify spawn source types
SPAWN_TYPE_KEYWORDS = {
    "vendor": ["VendorInventory", "Vendor", "merchant", "shop"],
    "loot_pool": ["LootSourceData", "LootTable", "loot", "drop"],
    "cerim_whisper": ["CerimWhisper", "Whisper", "cerim"],
    "chest": ["Chest", "chest", "TreasureChest"],
    "enemy_drop": ["EnemyDrop", "enemy", "Enemy"],
    "quest_reward": ["QuestReward", "quest", "Quest"],
    "crafting": ["Crafting", "Recipe", "recipe"],
}


def extract_strings(data: bytes, min_length: int = 4) -> list:
    """Extract readable ASCII strings from binary data."""
    strings = []
    current = []
    for b in data:
        if 32 <= b < 127:
            current.append(chr(b))
        else:
            if len(current) >= min_length:
                strings.append("".join(current))
            current = []
    if len(current) >= min_length:
        strings.append("".join(current))
    return strings


def classify_spawn_type(context_strings: list) -> str:
    """Classify spawn type based on context strings."""
    context_text = " ".join(context_strings).lower()

    # Check each spawn type by priority
    for spawn_type, keywords in SPAWN_TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in context_text:
                return spawn_type

    return "unknown"


def group_occurrences(occurrences: list) -> list:
    """Group occurrences by proximity into logical spawn sources."""
    if not occurrences:
        return []

    # Sort by offset
    sorted_occs = sorted(occurrences, key=lambda x: x["offset"])

    groups = []
    current_group = [sorted_occs[0]]

    for occ in sorted_occs[1:]:
        prev_offset = current_group[-1]["offset"]
        if occ["offset"] - prev_offset <= PROXIMITY_THRESHOLD:
            current_group.append(occ)
        else:
            groups.append(current_group)
            current_group = [occ]

    if current_group:
        groups.append(current_group)

    return groups


def build_spawn_source(group: list, bundle_name: str) -> dict:
    """Build a spawn source entry from a group of occurrences."""
    # Collect all context strings
    all_strings = []
    for occ in group:
        all_strings.extend(occ.get("strings", []))

    spawn_type = classify_spawn_type(all_strings)

    # Get offset range
    offsets = [occ["offset"] for occ in group]
    min_offset = min(offsets)
    max_offset = max(offsets)

    return {
        "bundle": bundle_name,
        "type": spawn_type,
        "occurrences": len(group),
        "offset_range": [min_offset, max_offset],
        "context_strings": list(set(s for s in all_strings if len(s) > 6))[:20],
    }


def search_patterns_worker(args):
    """Worker: search for a subset of patterns in file using mmap."""
    bundle_path, guid_patterns_serialized = args
    guid_patterns = {int(k): bytes.fromhex(v) for k, v in guid_patterns_serialized.items()}
    occurrences = defaultdict(list)

    file_size = Path(bundle_path).stat().st_size

    with open(bundle_path, "rb") as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            for guid, pattern in guid_patterns.items():
                pos = 0
                while True:
                    idx = mm.find(pattern, pos)
                    if idx == -1:
                        break

                    ctx_start = max(0, idx - CONTEXT_WINDOW // 2)
                    ctx_end = min(file_size, idx + CONTEXT_WINDOW // 2)
                    context = mm[ctx_start:ctx_end]
                    strings = extract_strings(context)

                    occurrences[guid].append({
                        "offset": idx,
                        "strings": strings,
                    })
                    pos = idx + 1

    return dict(occurrences)


def search_bundle_for_guids(
    bundle_path: Path,
    guid_patterns: dict,
    verbose: bool = False,
):
    """
    Search bundle for GUIDs using parallel pattern search.

    Splits patterns across workers - each worker mmaps the same file
    (OS shares pages) and searches for its subset of patterns.
    """
    if not guid_patterns:
        return {}

    # For small pattern counts, single-threaded is fine
    if len(guid_patterns) <= 50:
        return search_patterns_worker((str(bundle_path), {str(k): v.hex() for k, v in guid_patterns.items()}))

    # Split patterns across workers
    pattern_items = list(guid_patterns.items())
    chunk_size = max(1, len(pattern_items) // MAX_WORKERS)

    chunks = []
    for i in range(MAX_WORKERS):
        start = i * chunk_size
        end = len(pattern_items) if i == MAX_WORKERS - 1 else (i + 1) * chunk_size
        subset = dict(pattern_items[start:end])
        if subset:
            serialized = {str(k): v.hex() for k, v in subset.items()}
            chunks.append((str(bundle_path), serialized))

    occurrences_by_guid = defaultdict(list)

    with ProcessPoolExecutor(max_workers=min(MAX_WORKERS, len(chunks))) as executor:
        futures = [executor.submit(search_patterns_worker, chunk) for chunk in chunks]

        for i, future in enumerate(as_completed(futures)):
            if verbose:
                print(f"\r  Worker {i + 1}/{len(chunks)} done", end="", flush=True)
            result = future.result()
            for guid, occs in result.items():
                occurrences_by_guid[guid].extend(occs)

    if verbose:
        print()

    return occurrences_by_guid


def extract_spawn_locations(
    bundles_dir: Path,
    items: list,
    bundle_patterns: list = None,
    verbose: bool = False,
):
    """
    Extract spawn locations for all items from scene bundles.

    Args:
        bundles_dir: Path to bundles directory
        items: List of item dicts with 'id' and 'asset_guid' fields
        bundle_patterns: List of glob patterns for bundles to scan
        verbose: Print progress

    Returns:
        Dict mapping item_id -> list of spawn source dicts
    """
    if bundle_patterns is None:
        bundle_patterns = [
            "static_scenes_all_*.bundle",
            "world_scenes_all_*.bundle",
        ]

    # Build GUID -> pattern mapping
    guid_to_id = {}
    guid_patterns = {}

    for item in items:
        guid = item.get("asset_guid")
        if guid is None:
            continue
        item_id = item.get("id")
        if not item_id:
            continue

        guid_to_id[guid] = item_id
        guid_patterns[guid] = struct.pack("<Q", guid)

    if not guid_patterns:
        return {}

    if verbose:
        print(f"Searching for {len(guid_patterns)} item GUIDs...")

    # Collect all matching bundles
    bundles = []
    for pattern in bundle_patterns:
        for path in bundles_dir.glob(pattern):
            if path.is_file() and path not in bundles:
                bundles.append(path)

    spawn_locations = defaultdict(list)

    for bundle_path in sorted(bundles):
        file_size = bundle_path.stat().st_size
        size_mb = file_size / (1024 * 1024)

        if verbose:
            method = "parallel" if file_size > 2 * 1024 * 1024 * 1024 else "mmap"
            print(f"Scanning {bundle_path.name} ({size_mb:.1f} MB, {method})...", flush=True)

        occurrences_by_guid = search_bundle_for_guids(
            bundle_path,
            guid_patterns,
            verbose=verbose,
        )

        found_count = sum(len(occs) for occs in occurrences_by_guid.values())
        if verbose:
            print(f"\rScanning {bundle_path.name} ({size_mb:.1f} MB)... found {found_count} occurrences")

        # Process occurrences into spawn sources
        for guid, occurrences in occurrences_by_guid.items():
            item_id = guid_to_id[guid]
            groups = group_occurrences(occurrences)

            for group in groups:
                spawn_source = build_spawn_source(group, bundle_path.name)
                spawn_locations[item_id].append(spawn_source)

    return dict(spawn_locations)


def iter_bundles(bundles_dir: Path, pattern: str):
    """Iterate over bundle files matching pattern."""
    patterns = [p.strip() for p in pattern.split(",") if p.strip()]
    seen = set()
    for pat in patterns:
        for path in bundles_dir.glob(pat):
            if path.is_file() and path not in seen:
                seen.add(path)
                yield path


def main():
    parser = argparse.ArgumentParser(
        description="Extract spawn location data from scene bundles."
    )
    parser.add_argument(
        "--game-dir",
        default=DEFAULT_GAME_DIR,
        help="Game install root.",
    )
    parser.add_argument(
        "--bundles-dir",
        default="",
        help="Override bundles directory.",
    )
    parser.add_argument(
        "--items-json",
        default="",
        help="Path to items.json (default: out/items.json).",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output path for spawn locations JSON.",
    )
    parser.add_argument(
        "--bundle-pattern",
        default="static_scenes_all_*.bundle",
        help="Comma-separated glob patterns for bundles to scan.",
    )
    parser.add_argument(
        "--include-world-scenes",
        action="store_true",
        help="Also scan world_scenes_all_*.bundle (20GB, slow but finds world spawns).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print progress.",
    )
    parser.add_argument(
        "--item-filter",
        default="",
        help="Only process items matching this prefix (e.g., 'items.gear.weapons').",
    )

    args = parser.parse_args()

    game_dir = Path(args.game_dir)
    bundles_dir = Path(args.bundles_dir) if args.bundles_dir else game_dir / DEFAULT_BUNDLES_SUBDIR
    items_json_path = Path(args.items_json) if args.items_json else SCRIPT_DIR.parent / "out" / "items.json"
    output_path = Path(args.output) if args.output else SCRIPT_DIR.parent / "out" / "spawn_locations.json"

    if not bundles_dir.exists():
        print(f"Error: Bundles directory not found: {bundles_dir}", file=sys.stderr)
        sys.exit(1)

    if not items_json_path.exists():
        print(f"Error: items.json not found: {items_json_path}", file=sys.stderr)
        print("Run the main crawler first to generate items.json", file=sys.stderr)
        sys.exit(1)

    # Load items
    with open(items_json_path, "r", encoding="utf-8") as f:
        items = json.load(f)

    if args.item_filter:
        items = [item for item in items if item.get("id", "").startswith(args.item_filter)]
        if args.verbose:
            print(f"Filtered to {len(items)} items matching '{args.item_filter}'")

    bundle_patterns = [p.strip() for p in args.bundle_pattern.split(",") if p.strip()]
    if args.include_world_scenes and "world_scenes_all_*.bundle" not in bundle_patterns:
        bundle_patterns.append("world_scenes_all_*.bundle")

    spawn_locations = extract_spawn_locations(
        bundles_dir,
        items,
        bundle_patterns=bundle_patterns,
        verbose=args.verbose,
    )

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(spawn_locations, f, ensure_ascii=True, indent=2)

    total_sources = sum(len(locs) for locs in spawn_locations.values())
    print(f"Found spawn locations for {len(spawn_locations)} items ({total_sources} total sources)")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
