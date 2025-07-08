"""
Database migration script: add URL unique constraint

This script adds a unique constraint to the existing url_sources table to prevent concurrent duplicate URL creation.
"""

import sqlite3
import os

def migrate():
    db_path = "/app/data/basjoo.db"

    if not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        return False

    print(f"Starting database migration: {db_path}")

    backup_path = db_path + ".before_unique_constraint"
    import shutil
    shutil.copy2(db_path, backup_path)
    print(f"Database backed up to: {backup_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name='uq_agent_normalized_url'")
        existing = cursor.fetchone()

        if existing:
            print("Unique constraint already exists, skipping migration")
            return True

        print("Cleaning up duplicate URLs...")
        cursor.execute("""
            DELETE FROM url_sources
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM url_sources
                GROUP BY agent_id, normalized_url
            )
        """)
        deleted_count = cursor.rowcount
        print(f"  Deleted {deleted_count} duplicate records")

        print("Creating new table with unique constraint...")
        cursor.execute("""
            CREATE TABLE url_sources_new (
                id INTEGER PRIMARY KEY,
                agent_id VARCHAR(50) NOT NULL REFERENCES agents(id),
                url VARCHAR(1000) NOT NULL,
                normalized_url VARCHAR(1000) NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                last_fetch_at TIMESTAMP,
                last_error TEXT,
                title VARCHAR(500),
                content TEXT,
                content_hash VARCHAR(64),
                fetch_metadata JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                UNIQUE(agent_id, normalized_url)
            )
        """)

        print("Copying data...")
        cursor.execute("""
            INSERT INTO url_sources_new
            SELECT * FROM url_sources
        """)
        copied_count = cursor.rowcount
        print(f"  Copied {copied_count} records")

        print("Replacing table...")
        cursor.execute("DROP TABLE url_sources")
        cursor.execute("ALTER TABLE url_sources_new RENAME TO url_sources")

        print("Rebuilding index...")
        cursor.execute("CREATE INDEX ix_url_sources_agent_id ON url_sources (agent_id)")
        cursor.execute("CREATE INDEX ix_url_sources_url ON url_sources (url)")
        cursor.execute("CREATE INDEX ix_url_sources_normalized_url ON url_sources (normalized_url)")
        cursor.execute("CREATE INDEX ix_url_sources_status ON url_sources (status)")
        cursor.execute("CREATE INDEX ix_url_sources_agent_status ON url_sources (agent_id, status)")

        conn.commit()
        print("✅ Migration complete!")

        cursor.execute("SELECT COUNT(*) FROM url_sources")
        final_count = cursor.fetchone()[0]
        print(f"Final record count: {final_count}")

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
