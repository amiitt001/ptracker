# Firebase Setup Guide

Quick steps to connect Firebase Auth to the DSA Course Tracker.

---

## Step 1 — Create a Firebase Project

1. Go to [console.firebase.google.com](https://console.firebase.google.com)
2. Click **"Add project"** → Enter a name (e.g. `dsa-tracker`) → Create
3. Disable Google Analytics if you don't need it

---

## Step 2 — Register a Web App

1. In your project, click the **Web icon `</>`** → Register app
2. Give it a nickname (e.g. `DSA Tracker Web`)
3. **Copy the `firebaseConfig` object** shown on screen

---

## Step 3 — Paste Config into `firebase-config.js`

Open `/home/orion/project/dsa_tracker/firebase-config.js` and replace the placeholder values:

```js
const firebaseConfig = {
  apiKey:            "AIza...",
  authDomain:        "your-project.firebaseapp.com",
  projectId:         "your-project",
  storageBucket:     "your-project.firebasestorage.app",
  messagingSenderId: "12345678",
  appId:             "1:12345...",
};
```

---

## Step 4 — Enable Sign-In Methods

1. In Firebase Console → **Authentication** → **Sign-in method**
2. Enable **Email/Password** ✅
3. Enable **Google** ✅ (set your support email)

---

## Step 5 — Add Authorized Domains

1. Go to **Authentication** → **Settings** → **Authorized domains**
2. Add your deployment domain (e.g. `your-app.onrender.com`)
3. `localhost` is already allowed by default

---

## Step 6 (Optional) — Backend Token Verification

If you want the Flask backend to verify Firebase tokens:

1. Go to **Project Settings** → **Service Accounts**
2. Click **"Generate new private key"** → Download JSON
3. Save it as `backend/serviceAccountKey.json`
4. Install the Firebase Admin SDK:
   ```bash
   cd backend && venv/bin/pip install firebase-admin
   ```

> ⚠️ **Never commit `serviceAccountKey.json` or `firebase-config.js` with real values to git!**
> Both are already in `.gitignore`.

---

## Checklist

- [ ] `firebase-config.js` filled in
- [ ] Email/Password enabled in Firebase Console
- [ ] Google Sign-In enabled (optional)
- [ ] Deployment domain added to Authorized Domains
- [ ] `serviceAccountKey.json` placed in `backend/` (optional, for server-side verification)
