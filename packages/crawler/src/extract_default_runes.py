#!/usr/bin/env python3
"""
Extract default weapon rune pairs from scene bundles.
"""

import mmap
import os
import struct
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


DEFAULT_BUNDLE_PATTERN = "static_scenes_all_*.bundle"
MAX_WORKERS = min(8, os.cpu_count() or 4)

RUNE_MARKER_OFFSET = 80
RUNE_MARKER_BYTE = 0x22
RUNE_PAIR_BYTES = 1 + 16 + 8  # marker + rune1 entry + rune2 GUID


def iter_bundles(bundles_dir: Path, pattern: str):
    patterns = [p.strip() for p in pattern.split(",") if p.strip()]
    seen = set()
    for pat in patterns:
        for path in bundles_dir.glob(pat):
            if path.is_file() and path not in seen:
                seen.add(path)
                yield path


def search_patterns_worker(args):
    bundle_path, guid_patterns_serialized, rune_guid_map_serialized = args
    guid_patterns = {int(k): bytes.fromhex(v) for k, v in guid_patterns_serialized.items()}
    rune_guid_to_id = {
        int(guid): rune_id for guid, rune_id in (rune_guid_map_serialized or {}).items()
    }
    rune_pairs = defaultdict(list)

    file_size = Path(bundle_path).stat().st_size

    with open(bundle_path, "rb") as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            for guid, pattern in guid_patterns.items():
                pos = 0
                while True:
                    idx = mm.find(pattern, pos)
                    if idx == -1:
                        break
                    marker_offset = idx + RUNE_MARKER_OFFSET
                    if marker_offset + RUNE_PAIR_BYTES <= file_size:
                        if mm[marker_offset] == RUNE_MARKER_BYTE:
                            rune1_guid = struct.unpack_from("<Q", mm, marker_offset + 1)[0]
                            rune2_guid = struct.unpack_from("<Q", mm, marker_offset + 1 + 16)[0]
                            if rune1_guid in rune_guid_to_id and rune2_guid in rune_guid_to_id:
                                rune_pairs[guid].append((rune1_guid, rune2_guid))
                    pos = idx + 1

    return dict(rune_pairs)


def search_bundle_for_rune_pairs(
    bundle_path: Path,
    guid_patterns: dict,
    rune_guid_to_id: dict,
    verbose: bool = False,
):
    if not guid_patterns or not rune_guid_to_id:
        return {}

    rune_guid_map = {str(guid): rune_id for guid, rune_id in rune_guid_to_id.items()}

    if len(guid_patterns) <= 50:
        return search_patterns_worker(
            (str(bundle_path), {str(k): v.hex() for k, v in guid_patterns.items()}, rune_guid_map)
        )

    pattern_items = list(guid_patterns.items())
    chunk_size = max(1, len(pattern_items) // MAX_WORKERS)

    chunks = []
    for i in range(MAX_WORKERS):
        start = i * chunk_size
        end = len(pattern_items) if i == MAX_WORKERS - 1 else (i + 1) * chunk_size
        subset = dict(pattern_items[start:end])
        if subset:
            serialized = {str(k): v.hex() for k, v in subset.items()}
            chunks.append((str(bundle_path), serialized, rune_guid_map))

    rune_pairs_by_guid = defaultdict(list)

    with ProcessPoolExecutor(max_workers=min(MAX_WORKERS, len(chunks))) as executor:
        futures = [executor.submit(search_patterns_worker, chunk) for chunk in chunks]

        for i, future in enumerate(as_completed(futures)):
            if verbose:
                print(f"\r  Worker {i + 1}/{len(chunks)} done", end="", flush=True)
            result = future.result()
            for guid, pairs in result.items():
                rune_pairs_by_guid[guid].extend(pairs)

    if verbose:
        print()

    return dict(rune_pairs_by_guid)


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
    guid_patterns = {}

    for item in items:
        guid = item.get("asset_guid")
        item_id = item.get("id")
        if guid is None or not item_id:
            continue
        guid_to_item[guid] = item_id
        guid_patterns[guid] = struct.pack("<Q", guid)

    if not guid_patterns:
        return {}

    if verbose:
        print(f"Searching for {len(guid_patterns)} item GUIDs...")

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
            method = "parallel" if file_size > 2 * 1024 * 1024 * 1024 else "mmap"
            print(f"Scanning {bundle_path.name} ({size_mb:.1f} MB, {method})...", flush=True)

        rune_pairs_by_guid = search_bundle_for_rune_pairs(
            bundle_path,
            guid_patterns,
            rune_guid_to_id,
            verbose=verbose,
        )

        found_count = sum(len(pairs) for pairs in rune_pairs_by_guid.values())
        if verbose:
            print(f"\rScanning {bundle_path.name} ({size_mb:.1f} MB)... found {found_count} rune pairs")

        for guid, pairs in rune_pairs_by_guid.items():
            item_id = guid_to_item.get(guid)
            if not item_id:
                continue
            for pair in pairs:
                pair_counts[item_id][pair] += 1

    default_runes = {}
    for item_id, pairs in pair_counts.items():
        if not pairs:
            continue
        (rune1_guid, rune2_guid), _ = max(pairs.items(), key=lambda x: x[1])
        rune1_id = rune_guid_to_id.get(rune1_guid)
        rune2_id = rune_guid_to_id.get(rune2_guid)
        if rune1_id and rune2_id:
            default_runes[item_id] = [rune1_id, rune2_id]

    return default_runes
