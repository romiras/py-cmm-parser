import unittest
import sqlite3
import os
from domain import CMMEntity
from storage import SQLiteStorage


class TestSQLiteStorageV3(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_cmm_v3.db"
        # Ensure clean slate
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

        self.storage = SQLiteStorage(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_schema_creation(self):
        """Verify that v0.3 tables are created."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cursor.fetchall()]

        self.assertIn("files_v3", tables)
        self.assertIn("entities_v3", tables)
        self.assertIn("metadata", tables)
        self.assertIn("relations", tables)

        conn.close()

    def test_save_and_get_file(self):
        """Test saving and retrieving a file with entities."""
        file_path = "dummy_test.py"
        self.storage._compute_file_hash = lambda x: "dummy_hash"

        # Create a sample CMMEntity with hierarchy and dependencies
        entity_data = [
            {
                "name": "MyClass",
                "type": "class",
                "visibility": "public",
                "docstring": "A test class",
                "cmm_type": "Class",
                "dependencies": [{"name": "BaseClass", "rel_type": "inherits"}],
                "methods": [
                    {
                        "name": "my_method",
                        "type": "function",
                        "visibility": "public",
                        "docstring": "A method",
                        "cmm_type": "Method",
                        "method_kind": "instance",
                        "dependencies": [{"name": "helper", "rel_type": "calls"}],
                    }
                ],
            }
        ]

        cmm = CMMEntity(schema_version="v0.3", entities=entity_data)

        # Save
        self.storage.save_file(file_path, cmm)

        # Verify via direct DB inspection
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check entities_v3
        cursor.execute("SELECT name, type FROM entities_v3")
        rows = cursor.fetchall()
        names = sorted([r[0] for r in rows])
        self.assertEqual(names, ["MyClass", "my_method"])

        # Check relations
        cursor.execute("SELECT to_name, rel_type FROM relations")
        rels = sorted([(r[0], r[1]) for r in cursor.fetchall()])
        self.assertEqual(rels, [("BaseClass", "inherits"), ("helper", "calls")])

        conn.close()

        # Verify via get_file
        retrieved = self.storage.get_file(file_path)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.schema_version, "v0.3")
        self.assertEqual(len(retrieved.entities), 1)

        cls = retrieved.entities[0]
        self.assertEqual(cls["name"], "MyClass")
        self.assertEqual(len(cls["methods"]), 1)

        method = cls["methods"][0]
        self.assertEqual(method["name"], "my_method")
        self.assertEqual(method["dependencies"][0]["name"], "helper")
        self.assertEqual(method["dependencies"][0]["rel_type"], "calls")

    def test_upsert_file(self):
        """Test updating an existing file."""
        file_path = "/path/to/update.py"

        # Initial save
        # Need actual file for hash computation, so we mock _compute_file_hash or create file
        # Easier to mock _compute_file_hash by patching, but here we'll just create a dummy file
        with open("dummy_update.py", "w") as f:
            f.write("content 1")

        self.storage._compute_file_hash = lambda x: "hash1"

        cmm1 = CMMEntity(
            schema_version="v0.3", entities=[{"name": "OldClass", "type": "class"}]
        )

        self.storage.save_file(file_path, cmm1)

        # Verify OldClass exists
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM entities_v3 WHERE name='OldClass'")
        self.assertTrue(cursor.fetchone())
        conn.close()

        # Update
        self.storage._compute_file_hash = lambda x: "hash2"  # simulated change
        cmm2 = CMMEntity(
            schema_version="v0.3", entities=[{"name": "NewClass", "type": "class"}]
        )

        self.storage.upsert_file(file_path, cmm2)

        # Verify OldClass gone, NewClass exists
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM entities_v3 WHERE name='OldClass'")
        self.assertFalse(cursor.fetchone())

        cursor.execute("SELECT name FROM entities_v3 WHERE name='NewClass'")
        self.assertTrue(cursor.fetchone())
        conn.close()

        # Cleanup
        if os.path.exists("dummy_update.py"):
            os.remove("dummy_update.py")


if __name__ == "__main__":
    unittest.main()
