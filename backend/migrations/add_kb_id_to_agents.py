"""
Database migration script: add kb_id field to agents table (knowledge base association)

Supports multi-tenant isolated KB architecture; kb_id references knowledge_bases.id.
"""

import os
import shutil
import sqlite3


def migrate():
    possible_paths = [
        "/app/data/basjoo.db",
        "./test.db",
        "./data/basjoo.db",
        "../data/basjoo.db",
    ]
    db_path = next((p for p in possible_paths if os.path.exists(p)), None)
    if not db_path:
        print("Database file not found, skipping (new deployments handled by create_all)")
        return True

    print(f"Starting migration: {db_path}")
    backup = db_path + ".before_kb_id"
    shutil.copy2(db_path, backup)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA table_info(agents)")
        cols = [c[1] for c in cursor.fetchall()]
        if "kb_id" in cols:
            print("kb_id field already exists, skipping")
            return True

        print("Adding kb_id field...")
        cursor.execute("ALTER TABLE agents ADD COLUMN kb_id VARCHAR(36)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_agents_kb_id ON agents(kb_id)")
        conn.commit()
        print("✅ kb_id migration complete")
        return True
    except Exception as e:
        print(f"❌ Failed: {e}")
        conn.rollback()
        shutil.copy2(backup, db_path)
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
