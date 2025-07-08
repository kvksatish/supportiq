"""
Database migration script: add restricted_reply field to agents table and migrate old auto-reply data
"""

import os
import sqlite3
import shutil


COLUMNS = [
    ("restricted_reply", "TEXT"),
]

DEFAULT_REPLY = "Sorry, the service is currently restricted. Please try again later."


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

    backup_path = db_path + ".before_restricted_reply"
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

        if "restricted_reply" in columns or "restricted_reply" in added_columns:
            print("  Migrating auto-reply data to restricted_reply...")
            cursor.execute(
                """
                UPDATE agents
                SET restricted_reply = COALESCE(
                    NULLIF(rate_limit_reply, ''),
                    NULLIF(offline_reply, ''),
                    ?
                )
                WHERE restricted_reply IS NULL
                """,
                (DEFAULT_REPLY,),
            )

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
