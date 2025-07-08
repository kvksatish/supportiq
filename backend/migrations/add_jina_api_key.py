"""
Database migration script: add Jina API Key field
"""

import sqlite3
import os


def migrate():
    possible_paths = [
        "/app/data/basjoo.db",  # Docker environment
        "./test.db",             # Local development
        "./data/basjoo.db",      # Local development
        "../data/basjoo.db",     # Local development
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

    backup_path = db_path + ".before_jina_api_key"
    import shutil
    shutil.copy2(db_path, backup_path)
    print(f"Database backed up to: {backup_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(agents)")
        columns = [col[1] for col in cursor.fetchall()]

        if "jina_api_key" in columns:
            print("jina_api_key field already exists, skipping migration")
            return True

        print("  Adding jina_api_key...")
        cursor.execute("""
            ALTER TABLE agents
            ADD COLUMN jina_api_key VARCHAR(500)
        """)

        conn.commit()
        print("✅ Migration complete!")
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
