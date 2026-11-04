import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("migration", Path(__file__).parents[1] / "scripts" / "migrate_legacy.py")
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class MigrationTests(unittest.TestCase):
    def test_dry_run_migrate_restore_preserves_edits(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "main.py").write_text("# test fixture")
            original = root / "custom_nodes" / migration.LEGACY_PACKS[0]
            original.mkdir(parents=True)
            (original / "user-edit.txt").write_text("do not lose this edit")
            plan = migration.migrate(root)
            self.assertFalse(plan["applied"])
            self.assertTrue(original.exists())
            completed = migration.migrate(root, apply=True)
            self.assertFalse(original.exists())
            self.assertEqual(Path(completed["moves"][0]["backup"]).joinpath("user-edit.txt").read_text(), "do not lose this edit")
            migration.restore(completed["manifest"], apply=True)
            self.assertEqual((original / "user-edit.txt").read_text(), "do not lose this edit")


if __name__ == "__main__":
    unittest.main()
