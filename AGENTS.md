# iOS development

- Work from this repository root. This is independent of the sibling Android repository.
- Windows / PowerShell: begin commands with `chcp 65001 > $null`; use UTF-8 for text files.
- Reference Android behavior in `../hoshimi-localify-android/app/src/main/cpp/HoshimiLocalify` before implementing features. Preserve Android translation behavior.
- Do not modify the sibling Android repository without an explicit request.
- Shared translations are the `hoshimi-local` Git submodule. Keep its source data unchanged unless requested.
- Build: `./build-hook.ps1`. Run Python tests in `tools/`, with `build/test-runtime` on PYTHONPATH.
- Input IPA: `dump/ios/game.qualiarts.idolypride-<version>-Decrypted.ipa`. Re-discover addresses with `tools/discover_hook_profile.py` and `profiles/<version>.json`; follow `VERSION_PORTING.ko.md` for every game update. Never commit game IPAs, dumps, or build outputs.
- See README.ko.md for the complete packaging command.
- Keep the installed identity: display name 아이프라, bundle ID game.qualiarts.idolypride.kr. Update the existing app; do not uninstall it.
- v29 text translation and v30 image replacement were verified on device. Keep the static hooks.
- Minor home-loading stutter remains a measured-performance follow-up; its cause is not yet confirmed.

- Current target: 6.1.0 build 155 / patch 1.1.0. Read PORT_6.1.0.ko.md for metadata-based discovery, custom graphics, dictionary indexes and remote schema compatibility.
