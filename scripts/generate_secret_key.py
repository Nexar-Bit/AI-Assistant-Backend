"""
Generate a secure SECRET_KEY for the application.

Usage:
    python scripts/generate_secret_key.py
"""

import secrets
import sys


def generate_secret_key(length: int = 64) -> str:
    """
    Generate a cryptographically secure random secret key.
    
    Args:
        length: Length of the secret key in bytes (default: 64)
    
    Returns:
        A hexadecimal string secret key
    """
    return secrets.token_urlsafe(length)


if __name__ == "__main__":
    key = generate_secret_key()
    print("\n" + "=" * 70)
    print("SECRET_KEY Generated Successfully!")
    print("=" * 70)
    print(f"\n{key}\n")
    print("=" * 70)
    print("\nCopy this key and add it to your backend/.env file:")
    print(f"SECRET_KEY={key}\n")
    print("⚠️  IMPORTANT: Keep this key secret and never commit it to version control!\n")

