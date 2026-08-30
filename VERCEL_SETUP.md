# Vercel Deployment Guide for ptracker

This guide outlines how to deploy your **ptracker** Flask application on Vercel.

---

## 🚀 Option 1: Deploy via Vercel Web Dashboard (Recommended)

1. **Push your code to GitHub / GitLab / Bitbucket**:
   Ensure your repository is pushed to your Git provider.

2. **Import Project into Vercel**:
   - Go to [vercel.com/new](https://vercel.com/new).
   - Sign in and select your repository.
   - Framework Preset: Choose **Other** (Vercel automatically detects `vercel.json` and `app.py`).

3. **Configure Environment Variables**:
   In the project creation screen (or under **Settings -> Environment Variables** later), add the following environment variables:

| Environment Variable | Required | Description / Example |
|---|---|---|
| `SECRET_KEY` | **Yes** | A random secret string for session tokens (e.g., `supersecretkey123`) |
| `FIREBASE_API_KEY` | **Yes** | Your Firebase API Key |
| `FIREBASE_AUTH_DOMAIN` | **Yes** | `tracker-5a3c7.firebaseapp.com` |
| `FIREBASE_PROJECT_ID` | **Yes** | `tracker-5a3c7` |
| `FIREBASE_STORAGE_BUCKET` | **Yes** | `tracker-5a3c7.firebasestorage.app` |
| `FIREBASE_MESSAGING_SENDER_ID` | **Yes** | `909617946392` |
| `FIREBASE_APP_ID` | **Yes** | Your Firebase App ID |
| `FIREBASE_MEASUREMENT_ID` | Optional | `G-76Y4J7BJ6K` |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | **Yes** | Paste the full contents of your `serviceAccountKey.json` |
| `ROOT_FOLDER_ID` | **Yes** | Google Drive root folder ID (e.g. `1cUR2h1_e7kXgpdPc0q4zZ6afCU19ZkTy`) |
| `GOOGLE_DRIVE_TOKEN` | **Yes** | Output of `export_token.py` (base64 encoded token pickle) |

4. **Click Deploy**:
   Vercel will build your Python application and deploy it as a Serverless function globally!

---

## 🛠️ Option 2: Deploy via Vercel CLI

If you have Node.js and Vercel CLI installed:

1. Log in to Vercel in your terminal:
   ```bash
   npx vercel login
   ```

2. Run the deployment command from the project root:
   ```bash
   npx vercel
   ```

3. Follow the CLI prompts:
   - **Set up and deploy?** `Y`
   - **Which scope?** (Select your account)
   - **Link to existing project?** `N`
   - **Project Name:** `ptracker` (or your preferred name)
   - **Directory:** `./`

4. For production deployment:
   ```bash
   npx vercel --prod
   ```

---

## 📌 Technical Notes

- **Serverless Architecture**: All Flask routes (`/`, `/dashboard`, `/course`, `/player`, `/api/...`) are handled seamlessly by Vercel's Python Serverless Function environment (`@vercel/python`).
- **Database Path**: When deployed on Vercel (`VERCEL=1`), the SQLite database path automatically defaults to `/tmp/users.db` to accommodate Vercel's read-only serverless filesystem.
- **Firebase & Drive Authentication**: Provide `FIREBASE_SERVICE_ACCOUNT_JSON` and `GOOGLE_DRIVE_TOKEN` as environment variables in the Vercel dashboard so serverless instances can authenticate without needing physical local files.
