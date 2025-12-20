#!/usr/bin/env python3
"""Manual test for type hint capture via LSP."""

import tempfile
import sqlite3
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lsp_client import LSPClient
from storage import SQLiteStorage
from parser import TreeSitterParser


def main():
    # Create temporary workspace
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Create test file with type annotations
        test_file = workspace / "calculator.py"
        test_file.write_text("""
class Calculator:
    def add(self, x: int, y: int) -> int:
        '''Add two numbers.'''
        return x + y
    
    def multiply(self, a: float, b: float) -> float:
        '''Multiply two numbers.'''
        return a * b
""")

        db_path = workspace / "test.db"

        print(f"Workspace: {workspace}")
        print(f"Database: {db_path}")

        # Step 1: Parse and store
        parser = TreeSitterParser()
        storage = SQLiteStorage(str(db_path))

        cmm = parser.scan_file(str(test_file))
        storage.upsert_file(str(test_file), cmm)

        print("\nEntities scanned:")
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, type FROM entities")
        entities = cursor.fetchall()
        for eid, name, etype in entities:
            print(f"  {name} ({etype}): {eid}")

        # Step 2: Query LSP for type info
        lsp = LSPClient(str(workspace))
        if not lsp.start():
            print("\n❌ Failed to start LSP server")
            return

        print("\n✓ LSP server started")

        # Open the document
        file_uri = f"file://{test_file}"
        with open(test_file, "r") as f:
            lsp.open_document(file_uri, f.read())

        # Get type info for 'add' method (line 2, column 8)
        type_info = lsp.get_hover(file_uri, 2, 8)

        print(f"\nHover result for 'add': {type_info}")

        if type_info and type_info.signature:
            print(f"Signature: {type_info.signature}")

            # Save to DB
            cursor.execute("SELECT id FROM entities WHERE name = 'add'")
            add_id = cursor.fetchone()
            if add_id:
                storage.save_type_hint(add_id[0], type_info.signature)
                print("✓ Type hint saved for 'add'")

        # Verify
        cursor.execute("""
            SELECT e.name, m.type_hint 
            FROM entities e
            JOIN metadata m ON e.id = m.entity_id
            WHERE m.type_hint IS NOT NULL
        """)

        print("\nTypes captured:")
        for name, hint in cursor.fetchall():
            print(f"  {name}: {hint[:100]}")

        lsp.shutdown()
        conn.close()


if __name__ == "__main__":
    main()
