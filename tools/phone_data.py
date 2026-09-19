"""Compile Android phoneSubtitles.json into a bounded iOS runtime index."""

import json
import math
from pathlib import Path
import struct


MAGIC = b"HSPHONE1"
HEADER = struct.Struct("<8s7I")
CLIP = struct.Struct("<3I")
LINE = struct.Struct("<fI")


def compile_phone(root: Path):
    source = root / "local-files" / "phoneSubtitles.json"
    if not source.is_file():
        raise ValueError("hoshimi-local phoneSubtitles.json was not found")
    data = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("phoneSubtitles.json root must be an object")

    pool = bytearray(b"\0")

    def store(value: str):
        encoded = value.encode("utf-8")
        offset = len(pool)
        pool.extend(encoded)
        pool.append(0)
        return offset

    clips = []
    lines = []
    source_clips = len(data)
    source_lines = 0
    for name, raw_lines in sorted(data.items(), key=lambda item: item[0].encode("utf-8")):
        if not isinstance(name, str) or not name.startswith("sud_vo_phone"):
            raise ValueError(f"Invalid phone subtitle clip name: {name!r}")
        if not isinstance(raw_lines, list) or not raw_lines:
            raise ValueError(f"Phone subtitle clip has no lines: {name}")
        source_lines += len(raw_lines)
        compiled = []
        for ordinal, item in enumerate(raw_lines):
            if not isinstance(item, dict) or "time" not in item or "text" not in item:
                raise ValueError(f"Invalid phone subtitle line: {name}[{ordinal}]")
            timestamp = float(item["time"])
            text = item["text"]
            if not math.isfinite(timestamp) or timestamp < 0 or not isinstance(text, str):
                raise ValueError(f"Invalid phone subtitle value: {name}[{ordinal}]")
            text = text.replace("\\n", "\n")
            if not text:
                continue
            compiled.append((timestamp, int(item.get("line", ordinal)), text))
        if not compiled:
            continue
        compiled.sort(key=lambda item: (item[0], item[1]))
        first = len(lines)
        for timestamp, _, text in compiled:
            lines.append((timestamp, store(text)))
        clips.append((store(name), first, len(compiled)))

    clip_offset = HEADER.size
    line_offset = clip_offset + len(clips) * CLIP.size
    pool_offset = line_offset + len(lines) * LINE.size
    blob = bytearray(HEADER.pack(MAGIC, 1, len(clips), len(lines), clip_offset,
                                 line_offset, pool_offset, len(pool)))
    blob.extend(b"".join(CLIP.pack(*item) for item in clips))
    blob.extend(b"".join(LINE.pack(*item) for item in lines))
    blob.extend(pool)
    return bytes(blob), {
        "clips": len(clips),
        "lines": len(lines),
        "source_clips": source_clips,
        "source_lines": source_lines,
        "bytes": len(blob),
        "scope": "sud_vo_phone clip timeline subtitles",
    }
