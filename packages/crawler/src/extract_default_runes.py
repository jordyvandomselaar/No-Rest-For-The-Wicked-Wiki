#!/usr/bin/env python3
"""
Extract default weapon rune pairs from scene bundles.
"""

import mmap
import struct
from collections import defaultdict
from pathlib import Path


DEFAULT_BUNDLE_PATTERN = "static_scenes_all_*.bundle"

RUNE_MARKER_BYTE = 0x22
RUNE_MARKER = bytes([RUNE_MARKER_BYTE])
RUNE_ENTRY_SIZE = 16
MAX_RUNE_SLOTS = 4
WEAPON_SEARCH_WINDOW = 256


def iter_bundles(bundles_dir: Path, pattern: str):
    patterns = [p.strip() for p in pattern.split(",") if p.strip()]
    seen = set()
    for pat in patterns:
        for path in bundles_dir.glob(pat):
            if path.is_file() and path not in seen:
                seen.add(path)
                yield path


def parse_runes_at_marker(mm, marker_offset, file_size, rune_guid_set):
    if marker_offset + 1 + 8 > file_size:
        return None
    rune_guids = []
    for slot_index in range(MAX_RUNE_SLOTS):
        entry_offset = marker_offset + 1 + (RUNE_ENTRY_SIZE * slot_index)
        if entry_offset + 8 > file_size:
            break
        rune_guid = struct.unpack_from("<Q", mm, entry_offset)[0]
        if rune_guid == 0:
            break
        if rune_guid not in rune_guid_set:
            return None
        rune_guids.append(rune_guid)
    return rune_guids or None


def find_nearest_weapon_guid(mm, marker_offset, weapon_guid_set):
    start = max(0, marker_offset - WEAPON_SEARCH_WINDOW)
    offset = marker_offset - 8
    while offset >= start:
        guid = struct.unpack_from("<Q", mm, offset)[0]
        if guid in weapon_guid_set:
            return guid
        offset -= 8
    offset = marker_offset - 4
    while offset >= start:
        guid = struct.unpack_from("<Q", mm, offset)[0]
        if guid in weapon_guid_set:
            return guid
        offset -= 4
    return None


def scan_bundle_for_default_runes(bundle_path, weapon_guid_set, rune_guid_set, verbose=False):
    rune_pairs_by_weapon = defaultdict(list)
    file_size = Path(bundle_path).stat().st_size

    with open(bundle_path, "rb") as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            pos = 0
            while True:
                idx = mm.find(RUNE_MARKER, pos)
                if idx == -1:
                    break
                # quick filter: rune1 must be a valid rune GUID
                if idx + 1 + 8 <= file_size:
                    rune1_guid = struct.unpack_from("<Q", mm, idx + 1)[0]
                    if rune1_guid in rune_guid_set:
                        rune_guids = parse_runes_at_marker(mm, idx, file_size, rune_guid_set)
                        if rune_guids:
                            weapon_guid = find_nearest_weapon_guid(mm, idx, weapon_guid_set)
                            if weapon_guid:
                                rune_pairs_by_weapon[weapon_guid].append(tuple(rune_guids))
                pos = idx + 1

    if verbose:
        found_count = sum(len(pairs) for pairs in rune_pairs_by_weapon.values())
        print(f"\rScanning {bundle_path.name}... found {found_count} rune pairs")

    return dict(rune_pairs_by_weapon)


def extract_default_runes(
    bundles_dir: Path,
    items: list,
    bundle_patterns: list | None = None,
    rune_guid_to_id: dict | None = None,
    verbose: bool = False,
):
    if bundle_patterns is None:
        bundle_patterns = [DEFAULT_BUNDLE_PATTERN]

    if not rune_guid_to_id:
        return {}

    guid_to_item = {}
    weapon_guid_set = set()
    rune_guid_set = set(rune_guid_to_id.keys())

    for item in items:
        guid = item.get("asset_guid")
        item_id = item.get("id")
        if guid is None or not item_id:
            continue
        if not item_id.startswith("items.gear.weapons."):
            continue
        guid_to_item[guid] = item_id
        weapon_guid_set.add(guid)

    if not weapon_guid_set:
        return {}

    if verbose:
        print(f"Searching for {len(weapon_guid_set)} weapon GUIDs...")

    bundles = []
    for pattern in bundle_patterns:
        for path in bundles_dir.glob(pattern):
            if path.is_file() and path not in bundles:
                bundles.append(path)

    pair_counts = defaultdict(lambda: defaultdict(int))

    for bundle_path in sorted(bundles):
        file_size = bundle_path.stat().st_size
        size_mb = file_size / (1024 * 1024)

        if verbose:
            print(f"Scanning {bundle_path.name} ({size_mb:.1f} MB)...", flush=True)

        rune_pairs_by_guid = scan_bundle_for_default_runes(
            bundle_path,
            weapon_guid_set,
            rune_guid_set,
            verbose=verbose,
        )

        for guid, pairs in rune_pairs_by_guid.items():
            item_id = guid_to_item.get(guid)
            if not item_id:
                continue
            for rune_tuple in pairs:
                pair_counts[item_id][rune_tuple] += 1

    default_runes = {}
    for item_id, pairs in pair_counts.items():
        if not pairs:
            continue
        rune_tuple, _ = max(pairs.items(), key=lambda x: x[1])
        rune_ids = [rune_guid_to_id.get(guid) for guid in rune_tuple]
        if all(rune_ids):
            default_runes[item_id] = rune_ids

    return default_runes
