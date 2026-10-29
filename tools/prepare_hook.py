"""Generate build data from our translation JSON and the verified game IPA."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile

from package_probe import APP, UNITY, SOURCE_SHA256
from static_hook import plan, segments


def units(value):
    data = value.encode("utf-16-le")
    return struct.unpack("<" + "H" * (len(data) // 2), data)


def flatten(value):
    result = {}
    # nlohmann::json uses lexicographically sorted object keys in Local.cpp.
    for key, item in sorted(value.items()):
        if isinstance(item, dict):
            result.update(flatten(item))
        elif isinstance(item, str):
            result[key] = item
    return result


def prepare(ipa, translation, out, profile=None):
    source_sha256 = profile["ipa_sha256"] if profile else SOURCE_SHA256
    if hashlib.sha256(ipa.read_bytes()).hexdigest() != source_sha256:
        raise ValueError("IPA fingerprint mismatch")
    with zipfile.ZipFile(ipa) as archive:
        unity = archive.read(UNITY)
    hook = plan(unity, profile)
    # Validate the three API RVAs against symbols in the game's nlist table.
    from package_probe import commands
    needed = {"_il2cpp_string_chars", "_il2cpp_string_length", "_il2cpp_string_new",
              "_il2cpp_string_new_utf16"}
    exports = {}
    for pos, cmd, _ in commands(unity):
        if cmd != 2:
            continue
        symoff, count, stroff, strsize = struct.unpack_from("<4I", unity, pos + 8)
        for i in range(count):
            no, typ, sect, desc, address = struct.unpack_from("<IBBHQ", unity, symoff + 16 * i)
            if not no or no >= strsize:
                continue
            end = unity.find(b"\0", stroff + no, stroff + strsize)
            name = unity[stroff + no:end].decode("utf-8", errors="replace")
            if name in needed and typ & 0x0E == 0x0E:
                exports[name] = address
    if set(exports) != needed:
        raise ValueError("Missing IL2CPP string API symbols")
    source = translation.read_bytes()
    dictionary = flatten(json.loads(source.decode("utf-8-sig")))
    ordered = sorted(dictionary.items(), key=lambda item: units(item[0]))
    pool, entries = [], []
    for key, value in ordered:
        ku, vu = units(key), units(value)
        ko = len(pool)
        pool.extend(ku)
        vo = len(pool)
        pool.extend(vu)
        entries.append((ko, len(ku), vo, len(vu)))
    out.mkdir(parents=True, exist_ok=True)
    lines = ["/* Generated from existing Android localization.json. Do not edit. */",
             "#pragma once", "#include <stdint.h>",
             "struct Translation { uint32_t key, key_len, value, value_len; };",
             "static const uint16_t translation_pool[] = {"]
    for i in range(0, len(pool), 24):
        lines.append(",".join(map(str, pool[i:i + 24])) + ",")
    lines += ["};", "static const struct Translation translations[] = {"]
    lines.extend("{" + ",".join(map(str, e)) + "}," for e in entries)
    lines += ["};", f"#define TRANSLATION_COUNT {len(entries)}"]
    (out / "translations.h").write_text("\n".join(lines) + "\n", encoding="utf-8")
    version = profile["game_version"] if profile else "6.0.2"
    patch_version = profile["patch_version"] if profile else "1.0.0"
    header = [f"/* Verified against the {version} decrypted binary. */", "#pragma once",
              f'#define HOSHIMI_PATCH_VERSION "{patch_version}"']
    runtime_methods = profile["runtime_methods"] if profile else {
        "object_get_name": {"rva": 0x7843A14}, "set_multi_atlas": {"rva": 0x771CD08},
        "fallback_table": {"rva": 0x771CD98}, "clear_font_data": {"rva": 0x7724914},
        "audio_get_time": {"rva": 0x77D1284}, "audio_get_clip": {"rva": 0x77D13EC},
        "audio_clip_get_length": {"rva": 0x77CF84C}, "time_get_realtime": {"rva": 0x78471E8}}
    for name, offset in (profile.get("graphics_fields", {}) if profile else {}).items():
        header.append(f"#define HOSHIMI_FIELD_{name.upper()} {offset}")
    for name, method in runtime_methods.items():
        header.append(f"#define HOSHIMI_RUNTIME_{name.upper()}_RVA 0x{method['rva']:x}ULL")
    live_result = profile["sites"]["live_result"]["rva"] if profile else 0x1A17F20
    header.append(f"#define HOSHIMI_LIVE_RESULT_TARGET_RVA 0x{live_result:x}ULL")
    for key in ("target_rva", "cave_rva", "slot_rva", "original_rva",
                "font_target_rva", "font_cave_rva", "font_slot_rva", "font_original_rva"):
        header.append(f"#define HOSHIMI_{key.upper()} 0x{hook[key]:x}ULL")
    for key in ("adv_target_rva", "adv_cave_rva", "adv_slot_rva", "adv_original_rva"):
        header.append(f"#define HOSHIMI_{key.upper()} 0x{hook[key]:x}ULL")
    for key in ("master_target_rva", "master_cave_rva", "master_slot_rva", "master_original_rva"):
        header.append(f"#define HOSHIMI_{key.upper()} 0x{hook[key]:x}ULL")
    for name in ("tmp_set_text", "tmp_populate", "tmp_settext_bool", "tmp_setchararray",
                 "textfield", "ui_text", "image_sprite", "image_override",
                 "image_texture", "image_enable", "username_adv", "username_message",
                 "username_notification", "audio_play", "audio_play_u64",
                 "audio_delayed", "audio_oneshot", "audio_set_clip", "render_end",
                 "quality_fps", "quality_apply", "unity_fps",
                 "live_scene", *(profile.get("extra_sites", {}) if profile else {})):
        for suffix in ("target_rva", "cave_rva", "slot_rva", "original_rva"):
            key = f"{name}_{suffix}"
            header.append(f"#define HOSHIMI_{key.upper()} 0x{hook[key]:x}ULL")
    for name, address in sorted(exports.items()):
        header.append(f"#define API{name.upper()} 0x{address:x}ULL")
    for key in ("gateway_hex", "patched_entry_hex", "font_gateway_hex", "font_patched_entry_hex",
                "adv_gateway_hex", "adv_patched_entry_hex"):
        
        header.append("static const unsigned char " + key + "[] = {" +
                      ",".join(str(x) for x in bytes.fromhex(hook[key])) + "};")
    for key in ("master_gateway_hex", "master_patched_entry_hex"):
        header.append("static const unsigned char " + key + "[] = {" +
                      ",".join(str(x) for x in bytes.fromhex(hook[key])) + "};")
    for name in ("tmp_set_text", "tmp_populate", "tmp_settext_bool", "tmp_setchararray",
                 "textfield", "ui_text", "image_sprite", "image_override",
                 "image_texture", "image_enable", "username_adv", "username_message",
                 "username_notification", "audio_play", "audio_play_u64",
                 "audio_delayed", "audio_oneshot", "audio_set_clip", "render_end",
                 "quality_fps", "quality_apply", "unity_fps",
                 "live_scene", *(profile.get("extra_sites", {}) if profile else {})):
        for suffix in ("gateway_hex", "patched_entry_hex", "target_original_hex"):
            key = f"{name}_{suffix}"
            header.append("static const unsigned char " + key + "[] = {" +
                          ",".join(str(x) for x in bytes.fromhex(hook[key])) + "};")
    (out / "hook_profile.h").write_text("\n".join(header) + "\n", encoding="utf-8")
    hook.update({"translation_count": len(entries), "translation_sha256": hashlib.sha256(source).hexdigest(),
                 "string_api_rvas": exports})
    if profile:
        hook["profile"] = profile
    (out / "hook-plan.json").write_text(json.dumps(hook, indent=2) + "\n", encoding="utf-8")
    (out / "gateway.bin").write_bytes(bytes.fromhex(hook["gateway_hex"]))
    print(json.dumps({k: v for k, v in hook.items() if k != "gateway_hex"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ipa", required=True, type=Path)
    parser.add_argument("--translations", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--profile", type=Path, help="Saved version profile from discover_hook_profile.py")
    args = parser.parse_args()
    selected = json.loads(args.profile.read_text(encoding="utf-8")) if args.profile else None
    prepare(args.ipa, args.translations, args.out, selected)
