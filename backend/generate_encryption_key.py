#!/usr/bin/env python3
"""
Helper script to generate an encryption key.

Usage:
    python generate_encryption_key.py

This script generates a key suitable for use as the ENCRYPTION_KEY environment variable.
"""

import secrets
import base64


def generate_encryption_key() -> str:
    """Generate a secure encryption key"""
    key_bytes = secrets.token_bytes(32)
    key_b64 = base64.urlsafe_b64encode(key_bytes).decode('utf-8')
    return key_b64


def main():
    print("=" * 60)
    print("Basjoo API Key Encryption Key Generator")
    print("=" * 60)
    print()

    key = generate_encryption_key()

    print("Generated encryption key:")
    print("-" * 60)
    print(key)
    print("-" * 60)
    print()
    print("Usage:")
    print("1. Add the above key to your .env file:")
    print(f"   ENCRYPTION_KEY={key}")
    print()
    print("2. Or set the environment variable when starting the server:")
    print(f"   export ENCRYPTION_KEY={key}")
    print()
    print("⚠️  Important security notice:")
    print("   - Keep this key safe; losing it will make stored API Keys unrecoverable")
    print("   - Use a different key in production")
    print("   - Do not commit this key to version control")
    print()


if __name__ == "__main__":
    main()
