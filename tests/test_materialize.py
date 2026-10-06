import os
import tempfile
import unittest
from pathlib import Path

from voice2dir import materialize


class MaterializeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "tree"

    def tearDown(self):
        self.tmp.cleanup()

    def test_full_scheme_roundtrip(self):
        tree = {
            "greeting": "Hello, world!",
            "dir": {"subfile": "Content.\n", "subdir": {}},
            "symlink": ["link", "target path"],
            "script": ["script", "#!/bin/sh\necho Howdy!"],
        }
        materialize.materialize(tree, self.out)
        self.assertEqual(materialize.read_back(self.out), tree)
        self.assertTrue(materialize.verify(tree, self.out))

    def test_script_is_executable(self):
        tree = {"script": ["script", "echo hi\n"]}
        materialize.materialize(tree, self.out)
        path = self.out / "script"
        self.assertTrue(os.access(path, os.X_OK))

    def test_symlink_created(self):
        tree = {"alias": ["link", "does-not-exist"]}
        materialize.materialize(tree, self.out)
        path = self.out / "alias"
        self.assertTrue(path.is_symlink())
        self.assertEqual(os.readlink(path), "does-not-exist")

    def test_overwrite_removes_previous(self):
        materialize.materialize({"a": "old"}, self.out)
        materialize.materialize({"a": "new"}, self.out)
        self.assertEqual(materialize.read_back(self.out), {"a": "new"})

    def test_dir_replaced_by_file(self):
        materialize.materialize({"a": {"b": "c"}}, self.out)
        materialize.materialize({"a": "now a file"}, self.out)
        self.assertEqual(materialize.read_back(self.out), {"a": "now a file"})

    def test_dry_run_touches_nothing(self):
        materialize.materialize({"a": {"b": "c"}}, self.out, dry_run=True)
        self.assertFalse(self.out.exists())

    def test_root_must_be_object(self):
        with self.assertRaises(materialize.MaterializeError):
            materialize.materialize(["not", "an", "object"], self.out)  # type: ignore[arg-type]

    def test_bad_name_rejected(self):
        for name in ("", "..", "a/b"):
            with self.assertRaises(materialize.MaterializeError):
                materialize.materialize({name: "x"}, self.out)

    def test_bad_value_rejected(self):
        for value in (1, None, ["link"], ["script", 1], ["oops", "x"], ["link", 1]):
            with self.assertRaises(materialize.MaterializeError):
                materialize.materialize({"a": value}, self.out)

    def test_diff_trees_reports_all_kinds(self):
        desired = {"a": "old", "keep": 1 if False else "k", "gone": "x"}
        actual = {"a": "new", "keep": "k", "new": "y"}
        mismatches = materialize.diff_trees(desired, actual)
        self.assertIn("a: ожидалось 'old', получено 'new'", mismatches)
        self.assertIn("gone: отсутствует на диске", mismatches)
        self.assertIn("new: не содержится в желаемом дереве", mismatches)
        self.assertEqual(len(mismatches), 3)


if __name__ == "__main__":
    unittest.main()
