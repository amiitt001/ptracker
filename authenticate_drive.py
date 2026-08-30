#!/usr/bin/env python3
import base64
import os
import pickle
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend'))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import get_credentials, TOKEN_PATH

print("\n" + "=" * 60)
print("  🔑 Google Drive Authentication Helper")
print("=" * 60)
print("Opening browser for Google Sign-In...\n")

try:
    creds = get_credentials()
except Exception as e:
    print(f"❌ Error during authentication: {e}")
    sys.exit(1)

if creds and os.path.exists(TOKEN_PATH):
    with open(TOKEN_PATH, 'rb') as f:
        token = pickle.load(f)
    encoded = base64.b64encode(pickle.dumps(token)).decode()

    print("\n" + "=" * 60)
    print("  ✅ GOOGLE_DRIVE_TOKEN for Vercel:")
    print("=" * 60)
    print(f"\nGOOGLE_DRIVE_TOKEN={encoded}\n")
else:
    print("❌ token.pickle was not created.")
