"""
Database migration script: add offline_reply and error status fields to agents table
"""

import os
import sqlite3
import shutil


COLUMNS = [
    ("offline_reply", "TEXT"),
    ("last_error_code", "VARCHAR(50)"),
    ("last_error_message", "TEXT"),
    ("last_error_at", "DATETIME"),
]


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

    backup_path = db_path + ".before_offline_reply_and_error_status"
    shutil.copy2(db_path, backup_path)
    print(f"Database backed up to: {backup_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(agents)")
        columns = [col[1] for col in cursor.fetchall()]

        added_columns = []
        for column_name, column_def in COLUMNS:
            if column_name in columns:
                print(f"{column_name} field already exists, skipping")
                continue

            print(f"  Adding {column_name}...")
            cursor.execute(
                f"""
                ALTER TABLE agents
                ADD COLUMN {column_name} {column_def}
                """
            )
            added_columns.append(column_name)

        if not added_columns:
            print("All fields already exist, no migration needed")
            return True

        conn.commit()
        print("✅ Migration complete!")

        cursor.execute("PRAGMA table_info(agents)")
        new_columns = [col[1] for col in cursor.fetchall()]
        for column_name, _ in COLUMNS:
            if column_name not in new_columns:
                raise RuntimeError(f"{column_name} field was not added successfully")
            print(f"  ✓ {column_name} added")

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
