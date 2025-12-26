#!/usr/bin/env python3
import argparse
import json
import lzma
import struct
from pathlib import Path

from UnityPy import config as unity_config
from UnityPy.enums.BundleFile import ArchiveFlags, ArchiveFlagsOld, CompressionFlags
from UnityPy.helpers import CompressionHelper
from UnityPy.helpers.UnityVersion import UnityVersion
from UnityPy.streams import EndianBinaryReader


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_GAME_DIR = "/mnt/c/Program Files (x86)/Steam/steamapps/common/NoRestForTheWicked"
DEFAULT_BUNDLES_SUBDIR = "NoRestForTheWicked_Data/StreamingAssets/aa/StandaloneWindows64"


def iter_bundles(bundles_dir: Path, pattern: str):
    for path in sorted(bundles_dir.glob(pattern)):
        if path.is_file():
            yield path


def parse_unity_version(version_engine: str) -> UnityVersion:
    try:
        return UnityVersion.from_str(version_engine)
    except Exception:
        try:
            return UnityVersion.from_str(unity_config.get_fallback_version())
        except Exception:
            return UnityVersion.from_list(0, 0, 0)


def read_unityfs_header(reader: EndianBinaryReader):
    signature = reader.read_string_to_null()
    version = reader.read_int()
    version_player = reader.read_string_to_null()
    version_engine = reader.read_string_to_null()
    return signature, version, version_player, version_engine


def parse_flags(unity_version: UnityVersion, dataflags_value: int):
    if (
        unity_version < (2020,)
        or (unity_version[0] == 2020 and unity_version < (2020, 3, 34))
        or (unity_version[0] == 2021 and unity_version < (2021, 3, 2))
        or (unity_version[0] == 2022 and unity_version < (2022, 1, 1))
    ):
        return ArchiveFlagsOld(dataflags_value), ArchiveFlagsOld
    return ArchiveFlags(dataflags_value), ArchiveFlags


def decompress_block(data: bytes, uncompressed_size: int, flags: int) -> bytes:
    comp_flag = CompressionFlags(flags & ArchiveFlags.CompressionTypeMask)
    if comp_flag in CompressionHelper.DECOMPRESSION_MAP:
        return CompressionHelper.DECOMPRESSION_MAP[comp_flag](data, uncompressed_size)
    raise ValueError(f"Unsupported compression flag {comp_flag}")


def skip_bytes(reader: EndianBinaryReader, length: int):
    reader.Position += length


def read_unityfs_blocks(bundle_path: Path):
    reader = EndianBinaryReader(str(bundle_path))
    signature, bundle_version, _version_player, version_engine = read_unityfs_header(reader)
    if signature != "UnityFS":
        raise ValueError(f"Unsupported bundle signature: {signature}")

    size = reader.read_long()  # noqa: F841
    compressed_size = reader.read_u_int()
    uncompressed_size = reader.read_u_int()
    dataflags_value = reader.read_u_int()

    unity_version = parse_unity_version(version_engine)
    dataflags, flag_enum = parse_flags(unity_version, dataflags_value)

    if dataflags & dataflags.UsesAssetBundleEncryption:
        raise ValueError("Bundle uses asset bundle encryption; cannot scan without keys.")

    if bundle_version >= 7:
        reader.align_stream(16)
    elif unity_version >= (2019, 4):
        pre_align = reader.Position
        align_data = reader.read((16 - pre_align % 16) % 16)
        if any(align_data):
            reader.Position = pre_align

    start = reader.Position
    if dataflags & dataflags.BlocksInfoAtTheEnd:
        reader.Position = reader.Length - compressed_size
        blocks_info_bytes = reader.read_bytes(compressed_size)
        reader.Position = start
    else:
        blocks_info_bytes = reader.read_bytes(compressed_size)

    blocks_info = decompress_block(blocks_info_bytes, uncompressed_size, dataflags_value)
    blocks_reader = EndianBinaryReader(blocks_info, offset=start)

    blocks_reader.read_bytes(16)  # hash
    block_count = blocks_reader.read_int()
    blocks = []
    for _ in range(block_count):
        blocks.append(
            (
                blocks_reader.read_u_int(),
                blocks_reader.read_u_int(),
                blocks_reader.read_u_short(),
            )
        )

    nodes_count = blocks_reader.read_int()
    for _ in range(nodes_count):
        blocks_reader.read_long()  # offset
        blocks_reader.read_long()  # size
        blocks_reader.read_u_int()  # flags
        blocks_reader.read_string_to_null()

    if flag_enum is ArchiveFlags and dataflags & ArchiveFlags.BlockInfoNeedPaddingAtStart:
        reader.align_stream(16)

    return reader, blocks


def scan_lzma_stream(
    reader: EndianBinaryReader,
    compressed_len: int,
    needle_bytes,
    needle_keys,
    max_len: int,
    max_bytes: int,
    stop_after_found: bool,
    hits,
    scanned: int,
    carry: bytes,
    case_insensitive: bool,
):
    header = reader.read_bytes(5)
    if len(header) < 5:
        return scanned, carry, 0
    props, dict_size = struct.unpack("<BI", header)
    lc = props % 9
    remainder = props // 9
    pb = remainder // 5
    lp = remainder % 5
    dec = lzma.LZMADecompressor(
        format=lzma.FORMAT_RAW,
        filters=[
            {
                "id": lzma.FILTER_LZMA1,
                "dict_size": dict_size,
                "lc": lc,
                "lp": lp,
                "pb": pb,
            }
        ],
    )

    remaining = max(0, compressed_len - 5)
    pending = b""
    chunk_size = 1024 * 1024
    skipped = 0

    while remaining > 0 or pending:
        if not pending and remaining > 0:
            chunk = reader.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            pending = chunk

        limit = 0 if max_bytes == 0 else max_bytes - scanned
        if max_bytes and limit <= 0:
            break

        out = dec.decompress(pending, max_length=limit if limit > 0 else 0)
        pending = dec.unconsumed_tail

        if out:
            data = carry + out
            haystack = data.lower() if case_insensitive else data
            for needle, key in zip(needle_bytes, needle_keys):
                count = haystack.count(needle)
                if count:
                    hits[key] += count
            scanned += len(out)
            if stop_after_found and all(hits.values()):
                break
            if max_bytes and scanned >= max_bytes:
                break
            if max_len > 1:
                carry = data[-(max_len - 1) :]
            else:
                carry = b""

        if stop_after_found and all(hits.values()):
            break
        if max_bytes and scanned >= max_bytes:
            break

        if not pending and remaining == 0:
            break

    if remaining > 0:
        skip_bytes(reader, remaining)
        skipped += remaining

    return scanned, carry, skipped


def scan_raw_stream(
    reader: EndianBinaryReader,
    total_len: int,
    needle_bytes,
    needle_keys,
    max_len: int,
    max_bytes: int,
    stop_after_found: bool,
    hits,
    scanned: int,
    carry: bytes,
    case_insensitive: bool,
):
    remaining = total_len
    chunk_size = 1024 * 1024
    skipped = 0

    while remaining > 0:
        limit = 0 if max_bytes == 0 else max_bytes - scanned
        if max_bytes and limit <= 0:
            break
        to_read = min(chunk_size, remaining)
        chunk = reader.read(to_read)
        if not chunk:
            break
        remaining -= len(chunk)
        data = carry + chunk
        haystack = data.lower() if case_insensitive else data
        for needle, key in zip(needle_bytes, needle_keys):
            count = haystack.count(needle)
            if count:
                hits[key] += count
        scanned += len(chunk)
        if stop_after_found and all(hits.values()):
            break
        if max_bytes and scanned >= max_bytes:
            break
        if max_len > 1:
            carry = data[-(max_len - 1) :]
        else:
            carry = b""

    if remaining > 0:
        skip_bytes(reader, remaining)
        skipped += remaining

    return scanned, carry, skipped


def scan_bundle(
    bundle_path: Path,
    needle_bytes,
    needle_keys,
    max_len: int,
    max_bytes: int,
    stop_after_found: bool,
    max_block_bytes: int,
    allow_lzma: bool,
    case_insensitive: bool,
):
    hits = {needle: 0 for needle in needle_keys}
    carry = b""
    scanned = 0
    skipped_blocks = 0
    skipped_bytes = 0
    skipped_lzma = 0
    skipped_large = 0

    reader, blocks = read_unityfs_blocks(bundle_path)
    compression_counts = {}
    for uncompressed_len, compressed_len, flags in blocks:
        comp_flag = CompressionFlags(flags & ArchiveFlags.CompressionTypeMask)
        compression_counts[comp_flag] = compression_counts.get(comp_flag, 0) + 1

        if comp_flag == CompressionFlags.NONE:
            scanned, carry, skipped = scan_raw_stream(
                reader,
                compressed_len,
                needle_bytes,
                needle_keys,
                max_len,
                max_bytes,
                stop_after_found,
                hits,
                scanned,
                carry,
                case_insensitive,
            )
            if skipped:
                skipped_blocks += 1
                skipped_bytes += skipped
            if stop_after_found and all(hits.values()):
                break
            if max_bytes and scanned >= max_bytes:
                break
            continue

        if comp_flag == CompressionFlags.LZMA:
            if not allow_lzma:
                skip_bytes(reader, compressed_len)
                skipped_blocks += 1
                skipped_lzma += 1
                skipped_bytes += compressed_len
                continue
            scanned, carry, skipped = scan_lzma_stream(
                reader,
                compressed_len,
                needle_bytes,
                needle_keys,
                max_len,
                max_bytes,
                stop_after_found,
                hits,
                scanned,
                carry,
                case_insensitive,
            )
            if skipped:
                skipped_blocks += 1
                skipped_bytes += skipped
            if stop_after_found and all(hits.values()):
                break
            if max_bytes and scanned >= max_bytes:
                break
            continue

        if max_block_bytes and uncompressed_len > max_block_bytes:
            skip_bytes(reader, compressed_len)
            skipped_blocks += 1
            skipped_large += 1
            skipped_bytes += compressed_len
            continue

        compressed_data = reader.read_bytes(compressed_len)
        if not compressed_data:
            continue
        block = decompress_block(compressed_data, uncompressed_len, flags)
        if not block:
            continue
        data = carry + block
        haystack = data.lower() if case_insensitive else data
        for needle, key in zip(needle_bytes, needle_keys):
            count = haystack.count(needle)
            if count:
                hits[key] += count
        scanned += len(block)
        if stop_after_found and all(hits.values()):
            break
        if max_bytes and scanned >= max_bytes:
            break
        if max_len > 1:
            carry = data[-(max_len - 1) :]
        else:
            carry = b""

    stats = {
        "scanned_bytes": scanned,
        "skipped_blocks": skipped_blocks,
        "skipped_bytes": skipped_bytes,
        "skipped_lzma_blocks": skipped_lzma,
        "skipped_large_blocks": skipped_large,
        "compression_counts": {flag.name: count for flag, count in compression_counts.items()},
    }
    return hits, stats


def parse_needles(args):
    needles = []
    if args.needles:
        needles.extend([item for item in args.needles.split(",") if item])
    if args.needle:
        needles.extend(args.needle)
    if args.needles_file:
        for line in Path(args.needles_file).read_text(encoding="utf-8").splitlines():
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            needles.append(value)
    if not needles:
        needles = ["items.runes.", "UtilityRunes", "utility_runes"]
    if args.case_insensitive:
        needles = [needle.lower() for needle in needles]
    seen = set()
    deduped = []
    for needle in needles:
        if needle in seen:
            continue
        seen.add(needle)
        deduped.append(needle)
    return deduped


def main():
    parser = argparse.ArgumentParser(description="Lightweight UnityFS bundle scanner.")
    parser.add_argument("--game-dir", default=DEFAULT_GAME_DIR, help="Game install root.")
    parser.add_argument("--bundles-dir", default="", help="Override bundles directory.")
    parser.add_argument("--pattern", default="*.bundle", help="Glob pattern for bundles.")
    parser.add_argument("--needles", default="", help="Comma-separated needles to search for.")
    parser.add_argument("--needle", action="append", default=[], help="Needle to search for.")
    parser.add_argument("--needles-file", default="", help="Path to newline-delimited needles.")
    parser.add_argument("--case-insensitive", action="store_true", help="Lowercase both needles and data before matching.")
    parser.add_argument("--max-bytes", type=int, default=512 * 1024 * 1024, help="Max bytes to scan per bundle (0 = no limit).")
    parser.add_argument("--max-block-bytes", type=int, default=32 * 1024 * 1024, help="Skip blocks larger than this size (0 = no limit).")
    parser.add_argument("--allow-lzma", action="store_true", help="Allow scanning LZMA-compressed blocks.")
    parser.add_argument("--max-bundles", type=int, default=0, help="Stop after N bundles (0 = no limit).")
    parser.add_argument("--stop-after-found", action="store_true", help="Stop scanning a bundle once all needles are found.")
    parser.add_argument("--json", action="store_true", help="Output JSON lines instead of human-readable text.")
    args = parser.parse_args()

    game_dir = Path(args.game_dir)
    bundles_dir = Path(args.bundles_dir) if args.bundles_dir else game_dir / DEFAULT_BUNDLES_SUBDIR
    if not bundles_dir.exists():
        raise SystemExit(f"Bundles directory not found: {bundles_dir}")

    needles = parse_needles(args)
    needle_bytes = [needle.encode("utf-8") for needle in needles]
    max_len = max((len(n) for n in needle_bytes), default=1)
    max_bytes = args.max_bytes if args.max_bytes > 0 else 0
    max_block_bytes = args.max_block_bytes if args.max_block_bytes > 0 else 0

    scanned_bundles = 0
    for bundle_path in iter_bundles(bundles_dir, args.pattern):
        if args.max_bundles and scanned_bundles >= args.max_bundles:
            break
        scanned_bundles += 1

        try:
            hits, stats = scan_bundle(
                bundle_path,
                needle_bytes,
                needles,
                max_len,
                max_bytes,
                args.stop_after_found,
                max_block_bytes,
                args.allow_lzma,
                args.case_insensitive,
            )
            if args.json:
                payload = {
                    "bundle": bundle_path.name,
                    "size_bytes": bundle_path.stat().st_size,
                    **stats,
                    "hits": hits,
                }
                print(json.dumps(payload, ensure_ascii=True))
            else:
                summary = ", ".join(
                    f"{k}={v}" for k, v in hits.items() if v
                )
                if not summary:
                    summary = "no hits"
                skipped = stats["skipped_blocks"]
                note = f" | skipped {skipped} blocks" if skipped else ""
                print(f"{bundle_path.name} | scanned {stats['scanned_bytes']} bytes{note} | {summary}")
        except Exception as exc:
            if args.json:
                payload = {
                    "bundle": bundle_path.name,
                    "size_bytes": bundle_path.stat().st_size,
                    "error": str(exc),
                }
                print(json.dumps(payload, ensure_ascii=True))
            else:
                print(f"{bundle_path.name} | error: {exc}")


if __name__ == "__main__":
    main()
