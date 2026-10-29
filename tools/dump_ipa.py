"""Extract and run a local Il2CppDumper with version-specific output paths."""
import argparse
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile

from package_probe import APP, UNITY


def dump_ipa(ipa, dumper, output):
    dumper = dumper.resolve()
    if not dumper.is_file():
        raise ValueError("Install Il2CppDumper locally and pass --dumper <Il2CppDumper.exe>")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with ZipFile(ipa) as archive:
        (output / "UnityFramework").write_bytes(archive.read(UNITY))
        (output / "global-metadata.dat").write_bytes(
            archive.read(APP + "Data/Managed/Metadata/global-metadata.dat"))
    config_path = dumper.parent / "config.json"
    original = config_path.read_bytes()
    config = json.loads(original.decode("utf-8-sig"))
    config.update(RequireAnyKey=False, GenerateDummyDll=False)
    destination = output / "output"
    destination.mkdir(exist_ok=True)
    try:
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        with (output / "dumper.log").open("w", encoding="utf-8") as log:
            result = subprocess.run([str(dumper), str(output / "UnityFramework"),
                                     str(output / "global-metadata.dat"), str(destination)],
                                    stdout=log, stderr=subprocess.STDOUT, input="\n", text=True)
        if result.returncode or not (destination / "script.json").is_file():
            raise ValueError(f"Il2CppDumper failed; inspect {output / 'dumper.log'}")
    finally:
        config_path.write_bytes(original)
    print(f"Saved metadata identities: {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ipa", type=Path, required=True)
    parser.add_argument("--dumper", type=Path, default=Path("build/il2cppdumper/tool/Il2CppDumper.exe"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    dump_ipa(args.ipa, args.dumper, args.output)
