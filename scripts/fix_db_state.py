import sqlite3
import sys


def fix_database(db_path: str):
    print(f"Fixing database at {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 1. Clean up duplicate relations
        print("Cleaning duplicate relations...")
        cursor.execute("""
            DELETE FROM relations 
            WHERE rowid NOT IN (
                SELECT MIN(rowid) 
                FROM relations 
                GROUP BY from_id, to_name, rel_type
            )
        """)
        print(f"Removed {cursor.rowcount} duplicate relations.")

        # 2. Add missing columns (idempotent check)
        # SQLite doesn't support ADD COLUMN IF NOT EXISTS directly, so we check PRAGMA
        cursor.execute("PRAGMA table_info(entities_v3)")
        columns = [row[1] for row in cursor.fetchall()]

        if "line_start" not in columns:
            print("Adding line_start column...")
            cursor.execute(
                "ALTER TABLE entities_v3 ADD COLUMN line_start INTEGER DEFAULT 0"
            )

        if "line_end" not in columns:
            print("Adding line_end column...")
            cursor.execute(
                "ALTER TABLE entities_v3 ADD COLUMN line_end INTEGER DEFAULT 0"
            )

        # 3. Create Unique Index
        print("Creating unique index on relations...")
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_relations_unique ON relations(from_id, to_name, rel_type);"
        )

        conn.commit()
        print("Database fixed successfully.")

    except Exception as e:
        print(f"Error fixing database: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "../src/cmm.db"
    fix_database(db_path)
