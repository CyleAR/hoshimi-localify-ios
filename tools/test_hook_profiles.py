"""Integration checks for saved, version-locked IPA hook profiles."""
import json
from pathlib import Path
import unittest

from discover_hook_profile import discover, read_ipa
from static_hook import activate_profile, patch, plan


ROOT = Path(__file__).resolve().parent.parent


class HookProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_ipa = ROOT / "dump/ios/game.qualiarts.idolypride-6.0.2-Decrypted.ipa"
        cls.new_ipa = ROOT / "dump/ios/game.qualiarts.idolypride-6.0.3-Decrypted.ipa"
        if not cls.old_ipa.exists() or not cls.new_ipa.exists():
            raise unittest.SkipTest("Decrypted 6.0.2 and 6.0.3 IPAs are needed")
        cls.old_profile = json.loads((ROOT / "profiles/6.0.2.json").read_text(encoding="utf-8"))
        cls.new_profile = json.loads((ROOT / "profiles/6.0.3.json").read_text(encoding="utf-8"))
        _, cls.old_unity = read_ipa(cls.old_ipa)
        cls.new_info, cls.new_unity = read_ipa(cls.new_ipa)

    @classmethod
    def tearDownClass(cls):
        activate_profile(None)

    def test_saved_discovery_matches_new_ipa(self):
        found = discover(self.old_profile, self.old_unity, self.new_info,
                         self.new_unity, self.new_profile["patch_version"])
        self.assertEqual(found, self.new_profile)

    def test_plan_patches_and_rejects_wrong_binary(self):
        expected = plan(self.new_unity, self.new_profile)
        expected["profile"] = self.new_profile
        modified = patch(self.new_unity, expected)
        self.assertEqual(modified[expected["target_rva"]:expected["target_rva"] + 4],
                         bytes.fromhex(expected["patched_entry_hex"]))
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            plan(self.old_unity, self.new_profile)


if __name__ == "__main__":
    unittest.main()
