import pickle
import os
from google.auth.transport.requests import Request

TOKEN_PATH = '/home/orion/project/dsa_tracker/backend/token.pickle'

if os.path.exists(TOKEN_PATH):
    with open(TOKEN_PATH, 'rb') as f:
        creds = pickle.load(f)
    print(f"Token exists.")
    print(f"Valid: {creds.valid}")
    print(f"Expired: {creds.expired}")
    print(f"Has refresh token: {bool(creds.refresh_token)}")
    
    if creds.expired and creds.refresh_token:
        print("Attempting refresh...")
        try:
            creds.refresh(Request())
            print(f"Refresh successful. Valid: {creds.valid}")
        except Exception as e:
            print(f"Refresh failed: {e}")
else:
    print("Token does not exist.")
