#!/usr/bin/env python3
"""
Memory-efficient streaming search for weapon-rune relationships.
Streams files in chunks to keep memory low.
"""

import struct
from pathlib import Path

GAME_PATH = Path("/mnt/c/Program Files (x86)/Steam/steamapps/common/NoRestForTheWicked/NoRestForTheWicked_Data/StreamingAssets")

NITH_GATE_GUID = 4360494222496306584
PLAGUE_COLUMN_GUID = 1737564386904892761

# Byte patterns (little-endian uint64)
NITH_GATE_LE = struct.pack("<Q", NITH_GATE_GUID)
PLAGUE_COLUMN_LE = struct.pack("<Q", PLAGUE_COLUMN_GUID)

CHUNK_SIZE = 32 * 1024 * 1024  # 32MB chunks
PROXIMITY_WINDOW = 512  # Look for pairs within 512 bytes


def extract_strings(data: bytes) -> list:
    """Extract readable ASCII strings from binary data."""
    strings = []
    current = []
    for b in data:
        if 32 <= b < 127:
            current.append(chr(b))
        else:
            if len(current) >= 4:
                strings.append(''.join(current))
            current = []
    if len(current) >= 4:
        strings.append(''.join(current))
    return strings


def search_file_for_pairs(filepath: Path):
    """
    Stream through file looking for Nith Gate and Plague Column GUIDs
    appearing within PROXIMITY_WINDOW bytes of each other.
    """
    results = []
    file_size = filepath.stat().st_size

    with open(filepath, "rb") as f:
        offset = 0
        overlap = b""

        while offset < file_size:
            # Read chunk with overlap for boundary handling
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break

            search_data = overlap + chunk
            search_offset = offset - len(overlap)

            # Find all Nith Gate positions in this chunk
            nith_positions = []
            pos = 0
            while True:
                idx = search_data.find(NITH_GATE_LE, pos)
                if idx == -1 or idx >= len(chunk):
                    break
                nith_positions.append(search_offset + idx)
                pos = idx + 1

            # Find all Plague Column positions in this chunk
            plague_positions = []
            pos = 0
            while True:
                idx = search_data.find(PLAGUE_COLUMN_LE, pos)
                if idx == -1 or idx >= len(chunk):
                    break
                plague_positions.append(search_offset + idx)
                pos = idx + 1

            # Check for pairs within proximity window
            for nith_pos in nith_positions:
                for plague_pos in plague_positions:
                    distance = abs(nith_pos - plague_pos)
                    if 0 < distance <= PROXIMITY_WINDOW:
                        # Found a pair! Extract context
                        start = min(nith_pos, plague_pos) - 128
                        end = max(nith_pos, plague_pos) + 128

                        # Seek and read context
                        ctx_start = max(0, start - search_offset + len(overlap))
                        ctx_end = min(len(search_data), end - search_offset + len(overlap))
                        context = search_data[ctx_start:ctx_end]

                        results.append({
                            "nith_offset": nith_pos,
                            "plague_offset": plague_pos,
                            "distance": distance,
                            "context": context,
                        })

            # Keep overlap for boundary handling
            overlap = chunk[-PROXIMITY_WINDOW:] if len(chunk) >= PROXIMITY_WINDOW else chunk
            offset += len(chunk)

    return results


def main():
    bundles_to_search = [
        "static_scenes_all_566252beabc162772545543ac2741c85.bundle",
        "pooled_prefabs_assets_all_7fd52be0fd01120ed9275512ef91a036.bundle",
        "qdb_assets_all_031c9317807aff14922fc8f1c5b5e78d.bundle",
        "world_scenes_all_1118c50b0ad6420de0a560e221c7b2d9.bundle",
    ]

    bundle_dir = GAME_PATH / "aa" / "StandaloneWindows64"

    all_results = []

    for bundle_name in bundles_to_search:
        bundle_path = bundle_dir / bundle_name
        if not bundle_path.exists():
            print(f"Skipping (not found): {bundle_name}")
            continue

        size_mb = bundle_path.stat().st_size / (1024 * 1024)
        print(f"Scanning: {bundle_name} ({size_mb:.1f} MB)...", end=" ", flush=True)

        results = search_file_for_pairs(bundle_path)

        if results:
            print(f"FOUND {len(results)} pairs!")
            for r in results:
                print(f"\n  Nith Gate @ 0x{r['nith_offset']:X}")
                print(f"  Plague Column @ 0x{r['plague_offset']:X}")
                print(f"  Distance: {r['distance']} bytes")

                # Extract strings from context
                strings = extract_strings(r['context'])
                if strings:
                    print(f"  Strings: {strings[:10]}")

                all_results.append({
                    "bundle": bundle_name,
                    **r,
                    "strings": strings,
                })
        else:
            print("no pairs found")

    print(f"\n{'=' * 80}")
    print(f"SUMMARY: Found {len(all_results)} total pairs across all bundles")
    print(f"{'=' * 80}")

    for r in all_results:
        print(f"\n{r['bundle']}:")
        print(f"  Nith @ 0x{r['nith_offset']:X}, Plague @ 0x{r['plague_offset']:X}")
        print(f"  Strings: {r['strings'][:15]}")


if __name__ == "__main__":
    main()
