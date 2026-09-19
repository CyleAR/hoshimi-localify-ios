"""Compile localization.json into the reloadable iOS UTF-16 lookup index."""

import json
from pathlib import Path
import struct


MAGIC = b"HSLOC1\0\0"
HEADER = struct.Struct("<8s6I")
ENTRY = struct.Struct("<4I")


def _flatten(value):
    result = {}
    if not isinstance(value, dict):
        return result
    for key, item in sorted(value.items()):
        if isinstance(item, dict):
            result.update(_flatten(item))
        elif isinstance(item, str):
            result[key] = item
    return result


def _units(value):
    encoded = value.encode("utf-16-le")
    return struct.unpack("<" + "H" * (len(encoded) // 2), encoded)


def compile_localization(root: Path):
    source = root / "local-files" / "localization.json"
    if not source.is_file():
        raise ValueError("hoshimi-local localization.json was not found")
    document = json.loads(source.read_text(encoding="utf-8-sig"))
    items = sorted(_flatten(document).items(), key=lambda item: _units(item[0]))
    pool = []
    entries = []
    for key, value in items:
        key_units, value_units = _units(key), _units(value)
        key_offset = len(pool)
        pool.extend(key_units)
        value_offset = len(pool)
        pool.extend(value_units)
        entries.append((key_offset, len(key_units), value_offset, len(value_units)))
    entries_offset = HEADER.size
    pool_offset = entries_offset + len(entries) * ENTRY.size
    size = pool_offset + len(pool) * 2
    blob = bytearray(HEADER.pack(MAGIC, 1, len(entries), entries_offset,
                                 pool_offset, len(pool), size))
    blob.extend(b"".join(ENTRY.pack(*entry) for entry in entries))
    if pool:
        blob.extend(struct.pack("<" + "H" * len(pool), *pool))
    if len(blob) != size:
        raise AssertionError("localization binary size mismatch")
    return bytes(blob), {"entries": len(entries), "units": len(pool),
                         "bytes": len(blob), "scope": "localization.json"}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    payload, details = compile_localization(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(json.dumps(details, ensure_ascii=False, indent=2))
