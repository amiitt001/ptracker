import os
import pickle
import sys

# Ensure backend directory is in the import path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend'))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from google_auth_oauthlib.flow import InstalledAppFlow

TOKEN_PATH = os.path.join(backend_dir, 'token.pickle')
CREDS_PATH = os.path.join(backend_dir, 'credentials.json')
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

print(f"Removing old token from {TOKEN_PATH}")
if os.path.exists(TOKEN_PATH):
    os.remove(TOKEN_PATH)

print("Starting local server for Google Drive authentication...")
flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
creds = flow.run_local_server(port=5050, open_browser=False, access_type='offline', prompt='consent')

print("Authentication successful! Saving credentials...")
with open(TOKEN_PATH, 'wb') as f:
    pickle.dump(creds, f)

print(f"Token saved successfully at {TOKEN_PATH}!")
