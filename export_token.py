#!/usr/bin/env python3
"""
Export your local Google Drive token as a base64 env variable for deployment.

Usage:
  python export_token.py

Then copy the printed GOOGLE_DRIVE_TOKEN=... line into your deployment
platform's environment variables (Render dashboard, Railway, Heroku, etc.)
"""

import base64
import os
import pickle

TOKEN_PATH = os.path.join(os.path.dirname(__file__), 'backend', 'token.pickle')

if not os.path.exists(TOKEN_PATH):
    print("❌  token.pickle not found.")
    print("   Run  'python3 backend/app.py'  first to authenticate with Google.")
    exit(1)

with open(TOKEN_PATH, 'rb') as f:
    token = pickle.load(f)

encoded = base64.b64encode(pickle.dumps(token)).decode()

print("\n" + "=" * 60)
print("  ✅  Copy this into your deployment platform env vars:")
print("=" * 60)
print(f"\nGOOGLE_DRIVE_TOKEN={encoded}\n")
