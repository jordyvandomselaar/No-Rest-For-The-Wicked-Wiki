#!/usr/bin/env python3
"""
Find all rune GUIDs near Nith Gate locations in the asset files.
"""

import json
import struct
from pathlib import Path

GAME_PATH = Path("/mnt/c/Program Files (x86)/Steam/steamapps/common/NoRestForTheWicked/NoRestForTheWicked_Data/StreamingAssets")

NITH_GATE_GUID = 4360494222496306584
NITH_GATE_LE = struct.pack("<Q", NITH_GATE_GUID)

# Load rune GUIDs from items.json
def load_rune_guids():
    items_path = Path("packages/crawler/out/items.json")
    with open(items_path) as f:
        items = json.load(f)

    runes = {}
    for item in items:
        if item["id"].startswith("items.runes.") and item.get("asset_guid"):
            runes[item["asset_guid"]] = item["id"]
    return runes


def find_nith_gate_locations(filepath: Path):
    """Find all Nith Gate GUID locations in file."""
    locations = []
    chunk_size = 64 * 1024 * 1024

    with open(filepath, "rb") as f:
        offset = 0
        overlap = b""

        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break

            search_data = overlap + chunk
            search_offset = offset - len(overlap)

            pos = 0
            while True:
                idx = search_data.find(NITH_GATE_LE, pos)
                if idx == -1 or idx >= len(chunk):
                    break
                locations.append(search_offset + idx)
                pos = idx + 1

            overlap = chunk[-64:] if len(chunk) >= 64 else chunk
            offset += len(chunk)

    return locations


def search_runes_near_location(filepath: Path, location: int, rune_guids: dict, window: int = 512):
    """Search for rune GUIDs within window bytes of location."""
    found_runes = []

    start = max(0, location - window)
    end = location + window

    with open(filepath, "rb") as f:
        f.seek(start)
        data = f.read(end - start)

    for guid, rune_id in rune_guids.items():
        pattern = struct.pack("<Q", guid)
        pos = 0
        while True:
            idx = data.find(pattern, pos)
            if idx == -1:
                break
            actual_offset = start + idx
            distance = actual_offset - location
            found_runes.append({
                "rune_id": rune_id,
                "guid": guid,
                "offset": actual_offset,
                "distance": distance,
            })
            pos = idx + 1

    return found_runes


def main():
    rune_guids = load_rune_guids()
    print(f"Loaded {len(rune_guids)} rune GUIDs from items.json")

    bundle_path = GAME_PATH / "aa" / "StandaloneWindows64" / "static_scenes_all_566252beabc162772545543ac2741c85.bundle"

    print(f"\nFinding Nith Gate locations in {bundle_path.name}...")
    locations = find_nith_gate_locations(bundle_path)
    print(f"Found {len(locations)} Nith Gate occurrences")

    # Search for runes near each location
    all_runes = {}

    for loc in locations:
        runes = search_runes_near_location(bundle_path, loc, rune_guids, window=256)
        for r in runes:
            key = (r["rune_id"], r["distance"])
            if key not in all_runes:
                all_runes[key] = {
                    "rune_id": r["rune_id"],
                    "guid": r["guid"],
                    "distance": r["distance"],
                    "count": 0,
                }
            all_runes[key]["count"] += 1

    # Group by rune and show results
    runes_by_id = {}
    for key, data in all_runes.items():
        rune_id = data["rune_id"]
        if rune_id not in runes_by_id:
            runes_by_id[rune_id] = []
        runes_by_id[rune_id].append(data)

    print(f"\n{'=' * 80}")
    print("RUNES FOUND NEAR NITH GATE")
    print(f"{'=' * 80}")

    for rune_id, occurrences in sorted(runes_by_id.items()):
        print(f"\n{rune_id}")
        print(f"  GUID: {occurrences[0]['guid']}")
        for occ in sorted(occurrences, key=lambda x: x["distance"]):
            print(f"  Distance: {occ['distance']:+d} bytes, Count: {occ['count']}")


if __name__ == "__main__":
    main()
