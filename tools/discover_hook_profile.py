"""Discover version-locked hook RVAs from IL2CPP registration tables.

Run with a verified previous IPA/profile and the new decrypted IPA. Ambiguous
generic method matches fail closed; inspect them before distributing an IPA.
"""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import struct
from zipfile import ZipFile

import static_hook as legacy
from package_probe import APP, UNITY

FONT_METHODS = {
    "object_get_name": 0x7843A14,
    "set_multi_atlas": 0x771CD08,
    "fallback_table": 0x771CD98,
    "clear_font_data": 0x7724914,
}
RUNTIME_METHODS = {
    "audio_get_time": 0x77D1284,
    "audio_get_clip": 0x77D13EC,
    "audio_clip_get_length": 0x77CF84C,
    "time_get_realtime": 0x78471E8,
}
SPECIAL = {"username_adv", "username_message", "username_notification",
           "live_scene", "live_result"}
BASELINE_GLOBAL_METHOD_COUNTS = (0x3D546, 125701)


def read_ipa(path):
    raw = path.read_bytes()
    with ZipFile(path) as archive:
        info = plistlib.loads(archive.read(APP + "Info.plist"))
        unity = archive.read(UNITY)
    if info.get("CFBundleIdentifier") != "game.qualiarts.idolypride":
        raise ValueError("Unexpected game bundle ID")
    return {
        "game_version": info["CFBundleShortVersionString"],
        "game_build": info["CFBundleVersion"],
        "ipa_sha256": hashlib.sha256(raw).hexdigest(),
        "unity_sha256": hashlib.sha256(unity).hexdigest(),
    }, unity


def codegen_modules(data):
    seg = legacy.segments(data)["__DATA_CONST"]
    found = {}
    for pos in range(seg["offset"], seg["offset"] + seg["filesize"] - 24, 8):
        name, count, table = struct.unpack_from("<3Q", data, pos)
        if not (0x1000 < name < len(data) - 100 and 0 < count < 1000000 and
                seg["offset"] < table < len(data) - 8 * count):
            continue
        end = data.find(b"\0", name, name + 100)
        if end < 0:
            continue
        text = data[name:end]
        if not (text.endswith(b".dll") and all(32 <= c < 127 for c in text)):
            continue
        module = text.decode("ascii")
        if module in found:
            raise ValueError(f"Ambiguous IL2CPP module {module}")
        found[module] = {"rva": pos, "count": count, "table": table}
    return found


def method_rows(data, modules):
    addresses = {}
    for module, details in modules.items():
        table = details["table"]
        for index in range(details["count"]):
            address = struct.unpack_from("<Q", data, table + 8 * index)[0]
            if address:
                addresses.setdefault(address, []).append((module, index + 1))
    return addresses


def global_method_table(data, expected_count):
    """Locate one IL2CPP code-registration count/pointer pair, uniquely."""
    candidates = []
    needle = struct.pack("<Q", expected_count)
    start = 0
    while (offset := data.find(needle, start)) >= 0:
        start = offset + 1
        if offset % 8 or offset + 16 > len(data):
            continue
        table = struct.unpack_from("<Q", data, offset + 8)[0]
        if table % 8 == 0 and 0 < table <= len(data) - expected_count * 8:
            candidates.append({"registration_rva": offset, "count": expected_count,
                               "table_rva": table})
    if len(candidates) != 1:
        raise ValueError(f"Ambiguous global method pointer table: {len(candidates)} candidates")
    return candidates[0]


def legacy_sites():
    sites = {
        "i18n": legacy.TARGET,
        "font_awake": legacy.FONT_TARGET,
        "adv": legacy.ADV_TARGET,
        "master": legacy.MASTER_TARGET,
        "tmp_set_text": legacy.TMP_SET_TEXT_TARGET,
        "tmp_populate": legacy.TMP_POPULATE_TARGET,
        "tmp_settext_bool": legacy.TMP_SETTEXT_BOOL_TARGET,
        "tmp_setchararray": legacy.TMP_SETCHARARRAY_TARGET,
        "textfield": legacy.TEXTFIELD_TARGET,
        "ui_text": legacy.UI_TEXT_TARGET,
        "helper": legacy.HELPER,
        "live_result": legacy.LIVE_RESULT_TARGET,
    }
    for name, rva, _ in (legacy.IMAGE_SITES + legacy.USERNAME_SITES +
                         legacy.PHONE_SITES + legacy.GRAPHICS_SITES + legacy.LIVE_SITES):
        sites[name] = rva
    return sites


def baseline(path):
    info, data = read_ipa(path)
    if info["unity_sha256"] != legacy.UNITY_SHA256:
        raise ValueError("Baseline IPA does not match the verified 6.0.2 profile")
    modules = codegen_modules(data)
    reverse = method_rows(data, modules)
    method_tables = {str(count): global_method_table(data, count)
                     for count in BASELINE_GLOBAL_METHOD_COUNTS}
    sites = {}
    for name, rva in legacy_sites().items():
        rows = reverse.get(rva, [])
        if len(rows) != 1 and name not in SPECIAL:
            raise ValueError(f"Baseline method row is ambiguous: {name}: {rows}")
        site = {"rva": rva, "prologue": data[rva:rva + 16].hex()}
        if rows:
            site.update({"module": rows[0][0], "row": rows[0][1]})
        elif name in SPECIAL:
            matches = []
            for count, table in method_tables.items():
                start = table["table_rva"]
                end = start + table["count"] * 8
                slot = data.find(struct.pack("<Q", rva), start, end)
                if slot >= 0 and (slot - start) % 8 == 0:
                    matches.append((count, (slot - start) // 8))
                    if data.find(struct.pack("<Q", rva), slot + 8, end) >= 0:
                        matches.append((count, -1))
            if len(matches) != 1:
                raise ValueError(f"Global method pointer not unique: {name}")
            site["global_count"] = int(matches[0][0])
            site["global_index"] = matches[0][1]
        sites[name] = site
    methods = {}
    for name, rva in {**FONT_METHODS, **RUNTIME_METHODS}.items():
        rows = reverse.get(rva, [])
        if len(rows) != 1:
            raise ValueError(f"Baseline font method row is ambiguous: {name}")
        methods[name] = {"rva": rva, "module": rows[0][0], "row": rows[0][1]}
    return {**info, "patch_version": "1.0.0", "sites": sites,
            "runtime_methods": methods, "global_method_tables": method_tables,
            "codegen_module": {"name": "quaunity-ui.Runtime.dll",
                               "rva": modules["quaunity-ui.Runtime.dll"]["rva"]}}


def discover(previous, old_data, info, new_data, patch_version):
    if hashlib.sha256(old_data).hexdigest() != previous["unity_sha256"]:
        raise ValueError("Previous IPA does not match its saved profile")
    old_modules = codegen_modules(old_data)
    new_modules = codegen_modules(new_data)
    if set(old_modules) != set(new_modules):
        raise ValueError("IL2CPP module set changed; inspect metadata before porting")
    old_tables = {count: global_method_table(old_data, int(count))
                  for count in previous["global_method_tables"]}
    if old_tables != previous["global_method_tables"]:
        raise ValueError("Previous global method table moved or changed")
    new_tables = {count: global_method_table(new_data, int(count))
                  for count in old_tables}
    sites = {}
    for name, old in previous["sites"].items():
        if "module" not in old:
            continue
        module, row = old["module"], old["row"]
        prior, current = old_modules[module], new_modules[module]
        if prior["count"] != current["count"] or not 1 <= row <= current["count"]:
            raise ValueError(f"Method row layout changed: {name}")
        prior_rva = struct.unpack_from("<Q", old_data, prior["table"] + 8 * (row - 1))[0]
        rva = struct.unpack_from("<Q", new_data, current["table"] + 8 * (row - 1))[0]
        if prior_rva != old["rva"] or not 0x4000 <= rva < 0x978C000:
            raise ValueError(f"Method registration mismatch: {name}")
        if old_data[prior_rva:prior_rva + 4] != new_data[rva:rva + 4]:
            raise ValueError(f"Hook entry instruction changed: {name}")
        sites[name] = {"rva": rva, "prologue": new_data[rva:rva + 16].hex(),
                       "module": module, "row": row}
    for name, old in previous["sites"].items():
        if name in sites:
            continue
        index = old["global_index"]
        old_global = old_tables[str(old["global_count"])]
        new_global = new_tables[str(old["global_count"])]
        if not 0 <= index < old_global["count"]:
            raise ValueError(f"Global method index outside table: {name}")
        prior = struct.unpack_from("<Q", old_data, old_global["table_rva"] + 8 * index)[0]
        target = struct.unpack_from("<Q", new_data, new_global["table_rva"] + 8 * index)[0]
        if prior != old["rva"] or not 0x4000 <= target < 0x978C000:
            raise ValueError(f"Global method pointer mismatch: {name}")
        if old_data[prior:prior + 4] != new_data[target:target + 4]:
            raise ValueError(f"Global method entry instruction changed: {name}")
        sites[name] = {"rva": target, "prologue": new_data[target:target + 16].hex(),
                       "global_count": old["global_count"], "global_index": index}
    methods = {}
    for name, old in previous["runtime_methods"].items():
        module, row = old["module"], old["row"]
        prior, current = old_modules[module], new_modules[module]
        if prior["count"] != current["count"]:
            raise ValueError(f"Font method row layout changed: {name}")
        old_rva = struct.unpack_from("<Q", old_data, prior["table"] + 8 * (row - 1))[0]
        rva = struct.unpack_from("<Q", new_data, current["table"] + 8 * (row - 1))[0]
        if old_rva != old["rva"] or not 0x4000 <= rva < 0x978C000:
            raise ValueError(f"Font method registration mismatch: {name}")
        methods[name] = {"rva": rva, "module": module, "row": row}
    return {**info, "patch_version": patch_version, "sites": sites,
            "runtime_methods": methods, "global_method_tables": new_tables,
            "codegen_module": {"name": "quaunity-ui.Runtime.dll",
                               "rva": new_modules["quaunity-ui.Runtime.dll"]["rva"]},
            "discovery": {"previous_version": previous["game_version"],
                          "module_sites": sum("module" in s for s in sites.values()),
                          "global_method_sites": sum("global_index" in s for s in sites.values())}}



def semantic_discover(previous, old_data, info, new_data, old_script, new_script, patch_version):
    """Match exact Dumper method identities when registration rows have changed."""
    import re
    def identity(item):
        signature = re.sub(r"MethodInfo_[0-9A-Fa-f]+", "MethodInfo", item["Signature"])
        return (item["Name"], signature, item["TypeSignature"])
    old_methods = json.loads(old_script.read_text(encoding="utf-8-sig"))["ScriptMethod"]
    new_methods = json.loads(new_script.read_text(encoding="utf-8-sig"))["ScriptMethod"]
    by_address, by_identity = {}, {}
    for item in old_methods:
        by_address.setdefault(item["Address"], []).append(item)
    for item in new_methods:
        by_identity.setdefault(identity(item), []).append(item)
    modules = codegen_modules(new_data)
    reverse = method_rows(new_data, modules)
    def resolve(name, old):
        originals = by_address.get(old["rva"], [])
        matches = {}
        for original in originals:
            for candidate in by_identity.get(identity(original), []):
                matches[candidate["Address"]] = candidate
        if len(matches) != 1:
            raise ValueError(f"Method identity not unique: {name}: {len(matches)}")
        address, candidate = next(iter(matches.items()))
        if old_data[old["rva"]:old["rva"]+4] != new_data[address:address+4]:
            raise ValueError(f"Entry instruction changed: {name}")
        result = {"rva": address, "prologue": new_data[address:address+16].hex(),
                  "method_identity": list(identity(candidate))}
        rows = reverse.get(address, [])
        if len(rows) == 1:
            result.update(module=rows[0][0], row=rows[0][1])
        else:
            needle = struct.pack("<Q", address)
            slot = new_data.find(needle)
            if slot < 0 or slot % 8 or new_data.find(needle, slot+1) >= 0:
                raise ValueError(f"Method pointer slot not unique: {name}")
            result["pointer_slot_rva"] = slot
        return result
    if hashlib.sha256(old_data).hexdigest() != previous["unity_sha256"]:
        raise ValueError("Previous IPA does not match profile")
    return {**info, "patch_version": patch_version,
            "sites": {name: resolve(name, site) for name, site in previous["sites"].items()},
            "runtime_methods": {name: resolve(name, site) for name, site in previous["runtime_methods"].items()},
            "global_method_tables": {},
            "codegen_module": {"name": "quaunity-ui.Runtime.dll", "rva": modules["quaunity-ui.Runtime.dll"]["rva"]},
            "discovery": {"previous_version": previous["game_version"], "method": "exact_method_identity",
                          "old_script_sha256": hashlib.sha256(old_script.read_bytes()).hexdigest(),
                          "new_script_sha256": hashlib.sha256(new_script.read_bytes()).hexdigest()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-ipa", type=Path, required=True)
    parser.add_argument("--from-profile", type=Path)
    parser.add_argument("--to-ipa", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--patch-version", default="1.0.1")
    parser.add_argument("--from-script", type=Path)
    parser.add_argument("--to-script", type=Path)
    parser.add_argument("--to-dump", type=Path, help="Dumper dump.cs; adds custom graphics hooks")
    args = parser.parse_args()
    previous = json.loads(args.from_profile.read_text(encoding="utf-8")) if args.from_profile else baseline(args.from_ipa)
    if args.to_ipa:
        info, old_data = read_ipa(args.from_ipa)
        if info["ipa_sha256"] != previous["ipa_sha256"]:
            raise ValueError("Previous IPA SHA-256 differs from its saved profile")
        new_info, new_data = read_ipa(args.to_ipa)
        if args.from_script and args.to_script:
            profile = semantic_discover(previous, old_data, new_info, new_data, args.from_script, args.to_script, args.patch_version)
        else:
            profile = discover(previous, old_data, new_info, new_data, args.patch_version)
    else:
        profile = previous
    if args.to_dump:
        from graphics_profile import augment
        profile = augment(profile, new_data, args.to_script, args.to_dump)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {args.output}: {profile['game_version']} build {profile['game_build']}, "
          f"{len(profile['sites'])} hook sites")


if __name__ == "__main__":
    main()
