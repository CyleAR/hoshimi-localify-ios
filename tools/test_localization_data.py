import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest

from localization_data import compile_localization, HEADER, ENTRY, MAGIC


class LocalizationDataTests(unittest.TestCase):
    def test_compiles_utf16_sorted_flat_index(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "local-files" / "localization.json"
            source.parent.mkdir(parents=True)
            source.write_text(json.dumps({"group": {"나": "둘"}, "a": "하나"},
                                         ensure_ascii=False), encoding="utf-8")
            blob, details = compile_localization(root)
            magic, version, count, entries_offset, pool_offset, units, size = HEADER.unpack_from(blob)
            self.assertEqual((magic, version, count), (MAGIC, 1, 2))
            self.assertEqual(entries_offset, HEADER.size)
            self.assertEqual(size, len(blob))
            pool = struct.unpack_from("<" + "H" * units, blob, pool_offset)
            rows = [ENTRY.unpack_from(blob, entries_offset + i * ENTRY.size) for i in range(count)]
            decoded = []
            for key, key_len, value, value_len in rows:
                k = struct.pack("<" + "H" * key_len, *pool[key:key + key_len]).decode("utf-16-le")
                v = struct.pack("<" + "H" * value_len, *pool[value:value + value_len]).decode("utf-16-le")
                decoded.append((k, v))
            self.assertEqual(decoded, [("a", "하나"), ("나", "둘")])
            self.assertEqual(details["entries"], 2)


if __name__ == "__main__":
    unittest.main()
