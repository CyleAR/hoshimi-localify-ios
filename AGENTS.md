# iOS development

- Work from this repository root. This is independent of the sibling Android repository.
- Windows / PowerShell: begin commands with `chcp 65001 > $null`; use UTF-8 for text files.
- Reference Android behavior in `../hoshimi-localify-android/app/src/main/cpp/HoshimiLocalify` before implementing features. Preserve Android translation behavior.
- Do not modify the sibling Android repository without an explicit request.
- Shared translations are the `hoshimi-local` Git submodule. Keep its source data unchanged unless requested.
- Build: `./build-hook.ps1`. Run Python tests in `tools/`, with `build/test-runtime` on PYTHONPATH.
- Input IPA: `dump/ios/game.qualiarts.idolypride-6.0.2-Decrypted.ipa`. Never commit game IPAs, dumps, or build outputs.
- See README.ko.md for the complete packaging command.
- Keep the installed identity: display name 아이프라, bundle ID game.qualiarts.idolypride.kr. Update the existing app; do not uninstall it.
- v29 text translation and v30 image replacement were verified on device. Keep static hooks; the supplied Dobby requires debugger support and is not used by normal IPA builds.
- Minor home-loading stutter remains a measured-performance follow-up; its cause is not yet confirmed.
