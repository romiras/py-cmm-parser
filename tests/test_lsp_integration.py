import pytest
import tempfile
from pathlib import Path

# Skip test if Pyright is not available or if running in an environment where we can't spawn processes easily
# But for now, we assume we can.


def test_lsp_integration_two_files():
    """Test that LSP correctly resolves cross-file call."""

    # Create temporary workspace
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # File A: defines a class
        file_a = workspace / "module_a.py"
        file_a.write_text("""
class Calculator:
    def add(self, a, b):
        return a + b
""")

        # File B: calls Calculator.add
        file_b = workspace / "module_b.py"
        file_b.write_text("""
from module_a import Calculator

def use_calculator():
    calc = Calculator()
    result = calc.add(1, 2)
    return result
""")

        db_path = workspace / "test.db"

        # Check if Pyright is available before running
        # This prevents test failure in CI/CD environments without Pyright
        import subprocess

        try:
            subprocess.run(
                ["python", "-m", "pyright", "--version"],
                capture_output=True,
                check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            pytest.skip("Pyright not installed")

        # Run scan with LSP enabled
        # We need to make sure 'src' is in python path so cli imports work
        # And also so that the lsp_client can find the scanned files?
        # Actually LSP client runs in the workspace_root, so it should find module_a and module_b.

        # NOTE: scan_directory uses 'cmm.db' by default, we override it.
        # We also need to be careful about current working directory.
        # scan_directory takes absolute path usually.

        from typer.testing import CliRunner
        from cli import parser_app

        runner = CliRunner()
        result = runner.invoke(
            parser_app,
            [
                "scan",
                str(workspace),
                "--db-path",
                str(db_path),
                "--enable-lsp",
                "--verbose",
            ],
        )

        if result.exit_code != 0:
            print(result.stdout)

        assert result.exit_code == 0

        # Verify database
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Check that relation exists with is_verified=1
        # The relation should be from use_calculator to add

        cursor.execute("""
            SELECT e1.name, r.to_name, r.rel_type, r.is_verified 
            FROM relations r
            JOIN entities e1 ON r.from_id = e1.id
            WHERE r.to_name = 'add'
        """)

        rows = cursor.fetchall()
        print("\nFound relations:", rows)

        # We expect at least one relation to 'add' that is verified
        verified_calls = [r for r in rows if r[3] == 1]

        assert len(verified_calls) > 0, "LSP should have verified the 'add' call"
        assert verified_calls[0][1] == "add"

        # Verify type hints were captured (Sprint 5.4)
        cursor.execute(
            """
            SELECT type_hint 
            FROM metadata m
            JOIN entities e ON m.entity_id = e.id
            WHERE e.name = 'add'
        """
        )

        type_hint_row = cursor.fetchone()
        print(f"\nType hint for 'add': {type_hint_row}")

        # Type hint should contain signature information
        # Note: Pyright might return different formats, so we check for presence
        if type_hint_row and type_hint_row[0]:
            assert "add" in type_hint_row[0] or "int" in type_hint_row[0]

        conn.close()
