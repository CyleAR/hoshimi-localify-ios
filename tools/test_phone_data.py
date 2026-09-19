import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest

from phone_data import compile_phone, HEADER, CLIP, LINE, MAGIC


class PhoneDataTests(unittest.TestCase):
    def test_shared_translation_dataset(self):
        root = Path(__file__).resolve().parents[1] / "hoshimi-local"
        blob, details = compile_phone(root)
        self.assertTrue(blob.startswith(MAGIC))
        self.assertEqual(details["source_clips"], 514)
        self.assertEqual(details["source_lines"], 4681)
        self.assertEqual(details["clips"], 361)
        self.assertEqual(details["lines"], 4382)

    def test_compiles_sorted_clips_and_timeline(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "local-files" / "phoneSubtitles.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "sud_vo_phone_b": [{"line": 2, "time": 1.5, "text": "둘째"},
                                    {"line": 1, "time": 0, "text": "첫째\\n줄"}],
                "sud_vo_phone_a": [{"line": 1, "time": 0, "text": "가"}],
            }, ensure_ascii=False), encoding="utf-8")
            blob, details = compile_phone(root)
            magic, version, clips, lines, clip_off, line_off, pool_off, pool_size = HEADER.unpack_from(blob)
            self.assertEqual((magic, version, clips, lines), (MAGIC, 1, 2, 3))
            self.assertEqual(details["clips"], 2)
            pool = blob[pool_off:pool_off + pool_size]
            first_name, first_line, first_count = CLIP.unpack_from(blob, clip_off)
            self.assertEqual(pool[first_name:].split(b"\0", 1)[0].decode(), "sud_vo_phone_a")
            self.assertEqual((first_line, first_count), (0, 1))
            _, second_line, second_count = CLIP.unpack_from(blob, clip_off + CLIP.size)
            self.assertEqual((second_line, second_count), (1, 2))
            time0, text0 = LINE.unpack_from(blob, line_off + LINE.size)
            self.assertEqual(time0, 0)
            self.assertEqual(pool[text0:].split(b"\0", 1)[0].decode(), "첫째\n줄")

    def test_rejects_non_phone_clip(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "local-files" / "phoneSubtitles.json"
            path.parent.mkdir(parents=True)
            path.write_text('{"other": [{"time": 0, "text": "x"}]}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "clip name"):
                compile_phone(root)


if __name__ == "__main__":
    unittest.main()
