import base64
import hashlib
import json
import os
import pickle
import sqlite3
import time
import traceback

from dotenv import load_dotenv

# Load .env from the backend directory (where this file lives)
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BACKEND_DIR, '.env'))

from flask import Flask, Response, jsonify, request, send_file
import requests
import re
# import stripe  # Removed for production

from flask_cors import CORS
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

# Optional: Firebase Admin for server-side token verification
try:
    import firebase_admin
    from firebase_admin import credentials as fb_creds
    from firebase_admin import auth as fb_auth
    _FB_JSON = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON', '').strip()
    _FB_KEY = os.environ.get('FIREBASE_SERVICE_ACCOUNT', os.path.join(BACKEND_DIR, 'serviceAccountKey.json'))
    if _FB_KEY and not os.path.isabs(_FB_KEY):
        _FB_KEY = os.path.join(BACKEND_DIR, _FB_KEY)
    if _FB_JSON and not firebase_admin._apps:
        firebase_admin.initialize_app(fb_creds.Certificate(json.loads(_FB_JSON)))
        FIREBASE_ADMIN = True
    elif _FB_KEY and os.path.exists(_FB_KEY) and not firebase_admin._apps:
        firebase_admin.initialize_app(fb_creds.Certificate(_FB_KEY))
        FIREBASE_ADMIN = True
    else:
        FIREBASE_ADMIN = False
except (ImportError, ValueError, json.JSONDecodeError) as e:
    print(f"[firebase] Admin SDK not configured: {e}")
    FIREBASE_ADMIN = False

app = Flask(__name__)
CORS(app, origins="*")

# ── Paths ──────────────────────────────────────────────────────────
BASE_DIR   = BACKEND_DIR
HTML_DIR   = os.path.join(BASE_DIR, '..')
TOKEN_PATH = os.path.join(BASE_DIR, 'token.pickle')
CREDS_PATH = os.path.join(BASE_DIR, 'credentials.json')
DB_PATH    = os.environ.get('DATABASE_PATH', os.path.join(BASE_DIR, 'users.db'))
DB_DIR     = os.path.dirname(os.path.abspath(DB_PATH))
if DB_DIR:
    os.makedirs(DB_DIR, exist_ok=True)

# ── Config ─────────────────────────────────────────────────────────
SCOPES     = ['https://www.googleapis.com/auth/drive.readonly']
SECRET_KEY = os.environ.get('SECRET_KEY', 'dsa-tracker-change-in-production')
serializer = URLSafeTimedSerializer(SECRET_KEY)

# Stripe config removed


_service   = None



# ── Database ───────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=30000')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            email         TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS progress (
            uid TEXT PRIMARY KEY,
            state_json TEXT NOT NULL,
            is_paid BOOLEAN DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Try gracefully altering table if old schema exists
    try:
        conn.execute("ALTER TABLE progress ADD COLUMN is_paid BOOLEAN DEFAULT 0")
    except Exception:
        pass
    conn.commit()
    conn.close()


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.execute('PRAGMA busy_timeout=30000')
    conn.row_factory = sqlite3.Row
    return conn


init_db()   # runs on startup (works with gunicorn too)


def token_to_uid(raw_token: str) -> str:
    """Convert an opaque token to a deterministic legacy UID hash."""
    if not raw_token:
        return ''
    hash_val = hashlib.sha256(raw_token.encode()).hexdigest()
    return 'tok_' + hash_val[:60]


def decode_firebase_claims_unverified(raw_token: str) -> dict:
    """Read Firebase JWT payload when Admin SDK is unavailable.

    This is only a fallback for deployments that have not configured
    Firebase Admin yet. The frontend already obtained this token from
    Firebase; the stable uid avoids payment/progress loss when ID tokens
    rotate. Configure Firebase Admin in production for verification.
    """
    try:
        parts = raw_token.split('.')
        if len(parts) < 2:
            return {}
        payload = parts[1] + '=' * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
    except Exception:
        return {}


def decode_firebase_uid_unverified(raw_token: str) -> str:
    claims = decode_firebase_claims_unverified(raw_token)
    uid = claims.get('user_id') or claims.get('sub') or ''
    return str(uid)[:128]


def resolve_uid_from_auth_header(auth_header: str) -> str:
    """Resolve UID from Authorization header across Firebase Admin/non-Admin modes."""
    candidates = resolve_uid_candidates_from_auth_header(auth_header)
    return candidates[0] if candidates else ''


def resolve_uid_candidates_from_auth_header(auth_header: str) -> list:
    """Return primary uid plus legacy token-hash uid for old rows/sessions."""
    if not auth_header.startswith('Bearer '):
        return []
    raw_token = auth_header[7:]
    legacy_uid = token_to_uid(raw_token)
    primary_uid = ''
    if FIREBASE_ADMIN:
        try:
            decoded = fb_auth.verify_id_token(raw_token)
            primary_uid = decoded['uid']
        except Exception:
            return []
    else:
        primary_uid = decode_firebase_uid_unverified(raw_token) or legacy_uid

    return list(dict.fromkeys([uid for uid in (primary_uid, legacy_uid) if uid]))


def resolve_auth_email_from_header(auth_header: str) -> str:
    if not auth_header.startswith('Bearer '):
        return ''
    raw_token = auth_header[7:]
    if FIREBASE_ADMIN:
        try:
            decoded = fb_auth.verify_id_token(raw_token)
            return (decoded.get('email') or '').strip().lower()
        except Exception:
            return ''
    claims = decode_firebase_claims_unverified(raw_token)
    return (claims.get('email') or '').strip().lower()


def fetch_progress_for_uids(conn, uids):
    if not uids:
        return None
    placeholders = ','.join('?' for _ in uids)
    rows = conn.execute(
        f'SELECT uid, state_json, is_paid FROM progress WHERE uid IN ({placeholders})',
        uids
    ).fetchall()
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]

    primary_uid = uids[0]
    primary = next((row for row in rows if row['uid'] == primary_uid), None)
    state_json = '{}'
    if primary and primary['state_json'] != '{}':
        state_json = primary['state_json']
    else:
        non_empty = next((row['state_json'] for row in rows if row['state_json'] != '{}'), None)
        if non_empty:
            state_json = non_empty
    is_paid = 1 if any(row['is_paid'] for row in rows) else 0

    if primary:
        conn.execute(
            'UPDATE progress SET state_json = ?, is_paid = ?, updated_at = CURRENT_TIMESTAMP WHERE uid = ?',
            (state_json, is_paid, primary_uid)
        )
        for row in rows:
            if row['uid'] != primary_uid:
                conn.execute('DELETE FROM progress WHERE uid = ?', (row['uid'],))
    else:
        chosen = sorted(rows, key=lambda row: (not row['is_paid'], uids.index(row['uid'])))[0]
        conn.execute(
            'UPDATE progress SET uid = ?, state_json = ?, is_paid = ?, updated_at = CURRENT_TIMESTAMP WHERE uid = ?',
            (primary_uid, state_json, is_paid, chosen['uid'])
        )
        for row in rows:
            if row['uid'] != chosen['uid']:
                conn.execute('DELETE FROM progress WHERE uid = ?', (row['uid'],))
    conn.commit()
    return conn.execute('SELECT uid, state_json, is_paid FROM progress WHERE uid = ?', (primary_uid,)).fetchone()


def migrate_progress_uid(old_uid: str, new_uid: str):
    """Move legacy token-hash progress/payment to the stable Firebase uid."""
    if not old_uid or not new_uid or old_uid == new_uid:
        return
    conn = None
    try:
        conn = get_db()
        old = conn.execute('SELECT state_json, is_paid FROM progress WHERE uid = ?', (old_uid,)).fetchone()
        if not old:
            return
        new = conn.execute('SELECT state_json, is_paid FROM progress WHERE uid = ?', (new_uid,)).fetchone()
        if new:
            state_json = new['state_json'] if new['state_json'] != '{}' else old['state_json']
            is_paid = 1 if (new['is_paid'] or old['is_paid']) else 0
            conn.execute(
                'UPDATE progress SET state_json = ?, is_paid = ?, updated_at = CURRENT_TIMESTAMP WHERE uid = ?',
                (state_json, is_paid, new_uid)
            )
            conn.execute('DELETE FROM progress WHERE uid = ?', (old_uid,))
        else:
            conn.execute('UPDATE progress SET uid = ?, updated_at = CURRENT_TIMESTAMP WHERE uid = ?', (new_uid, old_uid))
        conn.commit()
    except Exception as e:
        print(f"[migrate_progress_uid] failed old={old_uid} new={new_uid}: {e}")
    finally:
        if conn:
            conn.close()


def mark_user_paid(uid: str, retries: int = 3) -> bool:
    return True # Always paid in production



# Stripe session validation removed



@app.route('/api/access/check', methods=['POST'])
def check_access():
    """Check whether current user has paid access (Always True in production)."""
    return jsonify({'is_paid': True, 'source': 'production_free'}), 200



# ── Auth endpoint ─────────────────────────────────────────────────
@app.route('/api/auth/verify')
def verify():
    """Verify a Firebase ID token (or skip if Firebase Admin is not configured)."""
    if not FIREBASE_ADMIN:
        # Firebase Admin not configured — trust frontend auth
        return jsonify({'status': 'ok', 'user': {'name': 'User'}}), 200

    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({'error': 'No token provided'}), 401

    id_token = auth_header[7:]
    try:
        decoded = fb_auth.verify_id_token(id_token)
        return jsonify({'user': {
            'id'   : decoded['uid'],
            'name' : decoded.get('name', decoded.get('email', 'User').split('@')[0]),
            'email': decoded.get('email', '')
        }})
    except Exception:
        return jsonify({'error': 'Invalid or expired token'}), 401


@app.route('/api/progress', methods=['GET', 'POST'])
def handle_progress():
    auth_header = request.headers.get('Authorization', '')
    uids = resolve_uid_candidates_from_auth_header(auth_header)
    if not uids:
        return jsonify({'error': 'No token provided'}), 401
    uid = uids[0]

    conn = get_db()
    
    if request.method == 'GET':
        row = fetch_progress_for_uids(conn, uids)
        conn.close()
        state = json.loads(row['state_json']) if row else {}
        return jsonify({'state': state, 'is_paid': True}), 200


    if request.method == 'POST':
        state_data = (request.get_json(silent=True) or {}).get('state', {})
        state_json = json.dumps(state_data)
        conn.execute('''
            INSERT INTO progress (uid, state_json, updated_at) 
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(uid) DO UPDATE SET 
                state_json=excluded.state_json, 
                updated_at=CURRENT_TIMESTAMP
        ''', (uid, state_json))
        conn.commit()
        conn.close()
        return jsonify({'status': 'ok'}), 200



@app.route('/api/redeem', methods=['POST'])
def redeem_code():
    auth_header = request.headers.get('Authorization', '')
    uid = resolve_uid_from_auth_header(auth_header)
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json or {}
    coupon_code = data.get('code', '').upper().strip()

    # Valid Access Codes are now managed via environment variables
    env_codes = os.environ.get('OFFER_CODES', '')
    VALID_FREE_CODES = [c.strip().upper() for c in env_codes.split(',') if c.strip()]

    if coupon_code in VALID_FREE_CODES:
        conn = get_db()
        conn.execute('''
            INSERT INTO progress (uid, state_json, is_paid)
            VALUES (?, '{}', 1)
            ON CONFLICT(uid) DO UPDATE SET is_paid = 1
        ''', (uid,))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'message': 'Code redeemed! Course unlocked.'}), 200
    else:
        return jsonify({'status': 'error', 'message': 'Invalid or expired coupon code.'}), 400

# ── Stripe Payment Endpoints ─────────────────────────────────────
# Stripe routes removed for production



# ── Page routes ────────────────────────────────────────────────────
@app.route('/')
def landing():
    return send_file(os.path.join(HTML_DIR, 'edustream.html'))

@app.route('/auth')
def auth_page():
    return send_file(os.path.join(HTML_DIR, 'auth.html'))

@app.route('/dashboard')
def dashboard():
    return send_file(os.path.join(HTML_DIR, 'dsa_tracker.html'))

@app.route('/edustream')
def edustream_page():
    return send_file(os.path.join(HTML_DIR, 'edustream.html'))

@app.route('/edustream_auth')
def edustream_auth_page():
    return send_file(os.path.join(HTML_DIR, 'edustream_auth.html'))

@app.route('/course')
def course_page():
    return send_file(os.path.join(HTML_DIR, 'course.html'))

@app.route('/player')
def player_page():
    return send_file(os.path.join(HTML_DIR, 'player.html'))

@app.route('/firebase-config.js')
def firebase_config():
    """Serve Firebase config + app config as JS, injected from env vars."""
    from flask import Response
    cfg = {
        'apiKey':            os.environ.get('FIREBASE_API_KEY', ''),
        'authDomain':        os.environ.get('FIREBASE_AUTH_DOMAIN', ''),
        'projectId':         os.environ.get('FIREBASE_PROJECT_ID', ''),
        'storageBucket':     os.environ.get('FIREBASE_STORAGE_BUCKET', ''),
        'messagingSenderId': os.environ.get('FIREBASE_MESSAGING_SENDER_ID', ''),
        'appId':             os.environ.get('FIREBASE_APP_ID', ''),
        'measurementId':     os.environ.get('FIREBASE_MEASUREMENT_ID', ''),
    }
    root_folder = os.environ.get('ROOT_FOLDER_ID', '')
    js = "// Auto-generated by Flask from environment variables\n"
    js += f"const firebaseConfig = {json.dumps(cfg, indent=2)};\n"
    js += f'const APP_CONFIG = {{ "rootFolder": "{root_folder}" }};\n'
    return Response(js, mimetype='application/javascript')


def get_service():
    global _service
    if _service:
        return _service

    creds = None
    token_env = os.environ.get('GOOGLE_DRIVE_TOKEN')
    if token_env:
        try:
            creds = pickle.loads(base64.b64decode(token_env.encode()))
        except Exception as e:
            print(f"⚠️  Token env var error: {e}")

    if not creds and os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, 'rb') as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            try:
                with open(TOKEN_PATH, 'wb') as f:
                    pickle.dump(creds, f)
            except Exception:
                pass
        else:
            if not os.path.exists(CREDS_PATH):
                raise RuntimeError("No Drive credentials found! See backend/SETUP.md")
            flow  = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(TOKEN_PATH, 'wb') as f:
                pickle.dump(creds, f)

    _service = build('drive', 'v3', credentials=creds)
    return _service


@app.route('/api/health')
def health():
    return jsonify({'status': 'ok'})

@app.route('/api/files/<folder_id>')
def list_files(folder_id):
    try:
        svc  = get_service()
        resp = svc.files().list(
            q        = f"'{folder_id}' in parents and trashed=false",
            fields   = "files(id, name, mimeType)",
            pageSize = 300
        ).execute()
        
        files = resp.get('files', [])
        
        # Natural sort so "10. Video" comes after "2. Video" instead of before
        def natural_keys(item):
            return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', item.get('name', ''))]
        
        files.sort(key=natural_keys)

        return jsonify({'files': files, 'folderId': folder_id})
    except RuntimeError as e:
        return jsonify({'error': str(e), 'setup_required': True}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stream/<file_id>')
def stream_video(file_id):
    is_paid = True # Always True in production


    svc = get_service()
    creds = svc._http.credentials
    # Refresh credentials if theoretically expired
    if not creds.valid and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            pass

    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    headers = {'Authorization': f'Bearer {creds.token}'}
    if 'Range' in request.headers:
        headers['Range'] = request.headers['Range']

    try:
        r = requests.get(url, headers=headers, stream=True)
        # Use generator to stream chunks safely
        def generate():
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    yield chunk

        resp = Response(generate(), status=r.status_code)
        # Forward necessary headers
        for key in ['Content-Type', 'Content-Length', 'Content-Range', 'Accept-Ranges']:
            if key in r.headers:
                resp.headers[key] = r.headers[key]
        return resp
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("=" * 54)
    print(f"  DSA Course Tracker  →  http://localhost:{port}")
    print("=" * 54)
    app.run(debug=False, port=5000, host='0.0.0.0')
