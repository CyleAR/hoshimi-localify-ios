"""Execute the production MasterDB range lookup on ARM64 index data."""
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn.arm64_const import (
    UC_ARM64_REG_LR, UC_ARM64_REG_SP, UC_ARM64_REG_X0, UC_ARM64_REG_X1,
    UC_ARM64_REG_X2, UC_ARM64_REG_X3,
)

from master_data import compile_master


ROOT = Path(__file__).resolve().parents[1]


class MasterRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT / "hook/hook.c").read_text(encoding="utf-8")
        structures = source[source.index("struct MasterHeader {"):source.index("static int load_master_index(")]
        search = source[source.index("static int master_prefix("):source.index("static int master_capitalize(")]
        support = r'''
#include <stddef.h>
#include <stdint.h>
static void *master_blob;
static uint32_t comparisons;
int strcmp(const char *a, const char *b) {
  ++comparisons;
  while (*a && *a == *b) { ++a; ++b; }
  return (unsigned char)*a - (unsigned char)*b;
}
int strncmp(const char *a, const char *b, size_t n) {
  for (size_t i = 0; i < n; ++i) {
    unsigned char x = (unsigned char)a[i], y = (unsigned char)b[i];
    if (x != y) return x - y;
    if (!x) return 0;
  }
  return 0;
}
'''
        wrapper = r'''
__attribute__((section(".entry"))) void run(void *blob, uint32_t table_index,
                                                const char *prefix, uint32_t *out) {
  master_blob = blob;
  comparisons = 0;
  const struct MasterHeader *header = (const struct MasterHeader *)blob;
  const char *base = (const char *)blob;
  const struct MasterTable *tables =
      (const struct MasterTable *)(base + sizeof(*header));
  const struct MasterEntry *entries =
      (const struct MasterEntry *)(base + sizeof(*header) +
                                    header->tables * sizeof(*tables) +
                                    header->fields * sizeof(uint32_t));
  const struct MasterTable *table = tables + table_index;
  uint32_t first = master_first_entry(header, entries, table, prefix);
  uint32_t count = 0;
  size_t length = 0;
  while (prefix[length]) ++length;
  for (uint32_t i = first; i < table->entry_start + table->entry_count; ++i) {
    const char *key = master_string(header, entries[i].key);
    if (!key || !master_prefix(key, prefix, length)) break;
    if (key[length]) ++count;
  }
  out[0] = first;
  out[1] = count;
  out[2] = comparisons;
}
'''
        llvm = Path(os.environ.get(
            "HOSHIMI_LLVM_BIN",
            str(Path(os.environ.get("LOCALAPPDATA", "")) /
                "Android/Sdk/ndk/26.3.11579264/toolchains/llvm/prebuilt/windows-x86_64/bin"),
        ))
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT / "build")
        path = Path(cls.temp.name)
        (path / "test.c").write_text(support + structures + search + wrapper, encoding="utf-8")
        (path / "link.ld").write_text(
            "SECTIONS { . = 0x100000; .text : { *(.entry) *(.text*) } "
            ".rodata : { *(.rodata*) } .data : { *(.data*) } .bss : { *(.bss*) } }",
            encoding="utf-8",
        )
        subprocess.run([str(llvm / "clang.exe"), "--target=aarch64-none-elf",
                        "-ffreestanding", "-fno-stack-protector", "-O1", "-c",
                        str(path / "test.c"), "-o", str(path / "test.o")], check=True)
        subprocess.run([str(llvm / "ld.lld.exe"), "-T", str(path / "link.ld"),
                        "--oformat=binary", str(path / "test.o"),
                        "-o", str(path / "test.bin")], check=True)
        cls.code = (path / "test.bin").read_bytes()

        data = {f"{i:04d}|name": f"번역{i}" for i in range(1024)}
        data["0420|levels[0].description"] = "첫 단계"
        data["0420|levels[1].description"] = "둘째 단계"
        root = path / "data"
        master = root / "local-files" / "masterTrans"
        master.mkdir(parents=True)
        (master / "Message.json").write_text(
            json.dumps({"rule": ["id|name", "id|levels.description"], "data": data},
                       ensure_ascii=False), encoding="utf-8")
        cls.blob, details = compile_master(root)
        assert details["entries"] == 1026

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def lookup(self, prefix):
        uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        uc.mem_map(0x100000, 0x1000000)
        uc.mem_write(0x100000, self.code)
        uc.mem_write(0x300000, self.blob)
        uc.mem_write(0x600000, prefix.encode("utf-8") + b"\0")
        uc.reg_write(UC_ARM64_REG_X0, 0x300000)
        uc.reg_write(UC_ARM64_REG_X1, 0)
        uc.reg_write(UC_ARM64_REG_X2, 0x600000)
        uc.reg_write(UC_ARM64_REG_X3, 0x700000)
        uc.reg_write(UC_ARM64_REG_SP, 0x900000)
        uc.reg_write(UC_ARM64_REG_LR, 0x200000)
        uc.emu_start(0x100000, 0x200000, count=200000)
        return struct.unpack("<3I", bytes(uc.mem_read(0x700000, 12)))

    def test_finds_only_matching_primary_key_fields(self):
        first, count, comparisons = self.lookup("0420|")
        self.assertEqual((first, count), (420, 3))
        self.assertLessEqual(comparisons, 11)
        self.assertEqual(self.lookup("0000|")[:2], (0, 1))
        self.assertEqual(self.lookup("1023|")[:2], (1025, 1))

    def test_missing_and_partial_primary_keys(self):
        self.assertEqual(self.lookup("1024|")[1], 0)
        self.assertEqual(self.lookup("042|")[1], 0)


if __name__ == "__main__":
    unittest.main()
