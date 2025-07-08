"""
Database migration script: add embedding_provider field

Adds the embedding_provider field to the agents table, supporting independent embedding provider selection (jina/siliconflow).
"""

import sqlite3
import os
import shutil


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

    backup_path = db_path + ".before_embedding_provider"
    shutil.copy2(db_path, backup_path)
    print(f"Database backed up to: {backup_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(agents)")
        columns = [col[1] for col in cursor.fetchall()]

        if "embedding_provider" in columns:
            print("embedding_provider field already exists, skipping migration")
            return True

        print("Adding embedding_provider field...")
        cursor.execute("""
            ALTER TABLE agents
            ADD COLUMN embedding_provider VARCHAR(20) DEFAULT 'jina'
        """)

        print("Backfilling existing data...")
        cursor.execute("""
            UPDATE agents
            SET embedding_provider = 'siliconflow'
            WHERE provider_type = 'siliconflow'
        """)

        conn.commit()
        print("✅ Migration complete!")

        cursor.execute("PRAGMA table_info(agents)")
        new_columns = [col[1] for col in cursor.fetchall()]
        if "embedding_provider" in new_columns:
            print("  ✓ embedding_provider added")
        else:
            print("  ✗ embedding_provider missing!")

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
