    #!/usr/bin/env python3
"""
Targeted search for specific item IDs in game asset files.
Streams files to keep memory usage low.
"""

import os
import sys
import struct
from pathlib import Path
from typing import List, Tuple

# IDs to search for
STRING_IDS = [
    b"items.gear.weapons.1Handed.wands.nithGate",
    b"items.runes.plagueColumn",
]

NUMERIC_IDS = [
    4360494222496306584,  # Nith Gate
    1737564386904892761,  # Plague Column
]

# Convert numeric IDs to byte patterns (little-endian and big-endian int64)
NUMERIC_PATTERNS: List[Tuple[bytes, str]] = []
for nid in NUMERIC_IDS:
    NUMERIC_PATTERNS.append((struct.pack("<q", nid), f"{nid} (LE signed)"))
    NUMERIC_PATTERNS.append((struct.pack(">q", nid), f"{nid} (BE signed)"))
    NUMERIC_PATTERNS.append((struct.pack("<Q", nid), f"{nid} (LE unsigned)"))
    NUMERIC_PATTERNS.append((struct.pack(">Q", nid), f"{nid} (BE unsigned)"))

CHUNK_SIZE = 64 * 1024 * 1024  # 64MB chunks for streaming


def search_file(filepath: Path, patterns: List[Tuple[bytes, str]]) -> List[Tuple[str, int, str]]:
    """
    Search a file for patterns using streaming.
    Returns list of (pattern_desc, offset, context) tuples.
    """
    results = []
    max_pattern_len = max(len(p[0]) for p in patterns)

    try:
        file_size = filepath.stat().st_size
        with open(filepath, "rb") as f:
            offset = 0
            overlap = b""

            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break

                # Combine with overlap from previous chunk
                search_data = overlap + chunk
                search_offset = offset - len(overlap)

                for pattern, desc in patterns:
                    pos = 0
                    while True:
                        idx = search_data.find(pattern, pos)
                        if idx == -1:
                            break

                        actual_offset = search_offset + idx
                        # Get context around the match
                        ctx_start = max(0, idx - 32)
                        ctx_end = min(len(search_data), idx + len(pattern) + 32)
                        context = search_data[ctx_start:ctx_end]

                        # Convert context to printable representation
                        ctx_str = repr(context)
                        if len(ctx_str) > 120:
                            ctx_str = ctx_str[:120] + "..."

                        results.append((desc, actual_offset, ctx_str))
                        pos = idx + 1

                # Keep overlap for patterns spanning chunk boundaries
                overlap = chunk[-max_pattern_len:] if len(chunk) >= max_pattern_len else chunk
                offset += len(chunk)

    except Exception as e:
        print(f"  Error reading {filepath}: {e}", file=sys.stderr)

    return results


def main():
    game_path = Path("/mnt/c/Program Files (x86)/Steam/steamapps/common/NoRestForTheWicked/NoRestForTheWicked_Data/StreamingAssets")

    if not game_path.exists():
        print(f"Game path not found: {game_path}")
        sys.exit(1)

    # Combine all patterns
    all_patterns: List[Tuple[bytes, str]] = []
    for sid in STRING_IDS:
        all_patterns.append((sid, sid.decode()))
    all_patterns.extend(NUMERIC_PATTERNS)

    print(f"Searching for {len(STRING_IDS)} string IDs and {len(NUMERIC_IDS)} numeric IDs")
    print(f"Total patterns: {len(all_patterns)}")
    print()

    # Collect files to search
    files_to_search = []

    # .bin files in StreamingAssets root
    for f in game_path.glob("*.bin"):
        files_to_search.append(f)

    # .bundle files
    bundle_path = game_path / "aa" / "StandaloneWindows64"
    if bundle_path.exists():
        for f in bundle_path.glob("*.bundle"):
            files_to_search.append(f)

    print(f"Files to search: {len(files_to_search)}")
    print()

    total_results = []

    for filepath in sorted(files_to_search):
        size_mb = filepath.stat().st_size / (1024 * 1024)
        print(f"Scanning: {filepath.name} ({size_mb:.1f} MB)...", end=" ", flush=True)

        results = search_file(filepath, all_patterns)

        if results:
            print(f"FOUND {len(results)} matches!")
            for desc, offset, ctx in results:
                print(f"  - {desc} @ offset {offset} (0x{offset:X})")
                print(f"    Context: {ctx}")
                total_results.append((filepath.name, desc, offset, ctx))
        else:
            print("no matches")

    print()
    print("=" * 80)
    print(f"SUMMARY: Found {len(total_results)} total matches")
    print("=" * 80)

    for fname, desc, offset, ctx in total_results:
        print(f"{fname}: {desc} @ 0x{offset:X}")


if __name__ == "__main__":
    main()
