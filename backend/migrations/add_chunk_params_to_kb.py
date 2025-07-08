"""Database migration: add chunk_size/chunk_overlap to knowledge_bases, add error_message/file_size fields.

Idempotent migration supporting multi-tenant KB document parsing pipeline.
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
    backup = db_path + ".before_chunk_params"
    shutil.copy2(db_path, backup)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        # knowledge_bases: chunk_size, chunk_overlap
        cursor.execute("PRAGMA table_info(knowledge_bases)")
        kb_cols = [c[1] for c in cursor.fetchall()]

        if "chunk_size" not in kb_cols:
            print("Adding chunk_size field...")
            cursor.execute(
                "ALTER TABLE knowledge_bases ADD COLUMN chunk_size INTEGER NOT NULL DEFAULT 512"
            )
        else:
            print("chunk_size already exists, skipping")

        if "chunk_overlap" not in kb_cols:
            print("Adding chunk_overlap field...")
            cursor.execute(
                "ALTER TABLE knowledge_bases ADD COLUMN chunk_overlap INTEGER NOT NULL DEFAULT 64"
            )
        else:
            print("chunk_overlap already exists, skipping")

        # kb_documents: error_message, file_size
        cursor.execute("PRAGMA table_info(kb_documents)")
        doc_cols = [c[1] for c in cursor.fetchall()]

        if "error_message" not in doc_cols:
            print("Adding error_message field...")
            cursor.execute("ALTER TABLE kb_documents ADD COLUMN error_message TEXT")
        else:
            print("error_message already exists, skipping")

        if "file_size" not in doc_cols:
            print("Adding file_size field...")
            cursor.execute("ALTER TABLE kb_documents ADD COLUMN file_size INTEGER")
        else:
            print("file_size already exists, skipping")

        conn.commit()
        print("✅ chunk_params migration complete")
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
