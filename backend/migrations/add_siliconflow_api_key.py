"""
Database migration script: add siliconflow_api_key field

Adds the siliconflow_api_key field to the agents table, supporting an independent SiliconFlow Embedding API Key.
"""

import sqlite3
import os
import shutil


def migrate():
    possible_paths = [
        "/app/data/basjoo.db",
        "./test.db",
        "./data/basjoo.db",
        "../data/basjoo.db",
    ]

    db_path = None
    for path in possible_paths:
        if os.path.exists(path):
            db_path = path
            break

    if not db_path:
        print(f"Database file not found, tried paths: {possible_paths}")
        return False

    print(f"Starting database migration: {db_path}")

    backup_path = db_path + ".before_siliconflow_api_key"
    shutil.copy2(db_path, backup_path)
    print(f"Database backed up to: {backup_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(agents)")
        columns = [col[1] for col in cursor.fetchall()]

        if "siliconflow_api_key" in columns:
            print("siliconflow_api_key field already exists, skipping migration")
            return True

        print("Adding siliconflow_api_key field...")
        cursor.execute("""
            ALTER TABLE agents
            ADD COLUMN siliconflow_api_key VARCHAR(500) DEFAULT ''
        """)

        conn.commit()
        print("✅ Migration complete!")

        cursor.execute("PRAGMA table_info(agents)")
        new_columns = [col[1] for col in cursor.fetchall()]
        if "siliconflow_api_key" in new_columns:
            print("  ✓ siliconflow_api_key added")
        else:
            print("  ✗ siliconflow_api_key missing!")

        return True

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        shutil.copy2(backup_path, db_path)
        print("Database restored from backup")
        return False

    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
