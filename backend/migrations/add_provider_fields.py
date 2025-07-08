"""
Database migration script: add AI provider support fields

This script adds multi-provider support fields to the agents table, including OpenAI, Anthropic, Google, and Azure OpenAI.
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

    backup_path = db_path + ".before_provider_fields"
    import shutil
    shutil.copy2(db_path, backup_path)
    print(f"Database backed up to: {backup_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(agents)")
        columns = [col[1] for col in cursor.fetchall()]

        if "provider_type" in columns:
            print("Provider fields already exist, skipping migration")
            return True

        print("Adding provider support fields...")

        # 1. provider_type (ENUM)
        print("  Adding provider_type...")
        cursor.execute("""
            ALTER TABLE agents
            ADD COLUMN provider_type VARCHAR(20) DEFAULT 'openai'
        """)

        print("  Adding azure_endpoint...")
        cursor.execute("""
            ALTER TABLE agents
            ADD COLUMN azure_endpoint VARCHAR(500)
        """)

        print("  Adding azure_deployment_name...")
        cursor.execute("""
            ALTER TABLE agents
            ADD COLUMN azure_deployment_name VARCHAR(100)
        """)

        print("  Adding azure_api_version...")
        cursor.execute("""
            ALTER TABLE agents
            ADD COLUMN azure_api_version VARCHAR(20)
        """)

        print("  Adding anthropic_version...")
        cursor.execute("""
            ALTER TABLE agents
            ADD COLUMN anthropic_version VARCHAR(20)
        """)

        print("  Adding google_project_id...")
        cursor.execute("""
            ALTER TABLE agents
            ADD COLUMN google_project_id VARCHAR(100)
        """)

        print("  Adding google_region...")
        cursor.execute("""
            ALTER TABLE agents
            ADD COLUMN google_region VARCHAR(50)
        """)

        print("  Adding provider_config...")
        cursor.execute("""
            ALTER TABLE agents
            ADD COLUMN provider_config JSON
        """)

        print("  Adding modified_system_presets...")
        cursor.execute("""
            ALTER TABLE agents
            ADD COLUMN modified_system_presets JSON
        """)

        conn.commit()
        print("✅ Migration complete!")

        cursor.execute("PRAGMA table_info(agents)")
        new_columns = [col[1] for col in cursor.fetchall()]
        print(f"agents table now has {len(new_columns)} fields")

        required_fields = [
            "provider_type",
            "azure_endpoint",
            "azure_deployment_name",
            "azure_api_version",
            "anthropic_version",
            "google_project_id",
            "google_region",
            "provider_config",
            "modified_system_presets"
        ]

        for field in required_fields:
            if field in new_columns:
                print(f"  ✓ {field} added")
            else:
                print(f"  ✗ {field} missing!")

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
