# Google Drive API Setup Guide

## Steps

1. **Go to Google Cloud Console**  
   https://console.cloud.google.com/

2. **Create / select a project**  
   Top bar → project dropdown → New Project

3. **Enable Google Drive API**  
   APIs & Services → Library → search "Google Drive API" → Enable

4. **Create OAuth credentials**  
   APIs & Services → Credentials → Create Credentials → OAuth client ID  
   - Application type: **Desktop App**  
   - Name: *DSA Tracker*  
   - Click **Create**

5. **Download & rename**  
   Click the download icon → rename file to **`credentials.json`**  
   Place it in this `backend/` directory.

6. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

7. **Run the backend**
   ```bash
   python app.py
   ```
   A browser tab opens for Google Sign-In.  
   Log in with the account that owns the Drive folders → Grant access.  
   Token is saved as `token.pickle` — future runs auto-authenticate.

8. **Open the tracker**  
   Visit http://localhost:5000 — videos will play directly inside the app!

---

> **Note:** Make sure your Google account has access to the Drive folders  
> containing the DSA videos.
