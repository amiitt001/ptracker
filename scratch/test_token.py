import pickle
import os
import base64
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

TOKEN_PATH = '/home/orion/project/dsa_tracker/backend/token.pickle'

with open(TOKEN_PATH, 'rb') as f:
    creds = pickle.load(f)

print(f"Token valid: {creds.valid}")
print(f"Token expired: {creds.expired}")
print(f"Has refresh token: {bool(creds.refresh_token)}")

try:
    print("Attempting refresh...")
    creds.refresh(Request())
    print("Refresh successful!")
except Exception as e:
    print(f"Refresh failed: {e}")
