import base64
import json
import os
import pickle
import sqlite3

from dotenv import load_dotenv

# Load .env from the backend directory (where this file lives)
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

from flask import Flask, Response, jsonify, request, send_file
import requests
import re
import stripe
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
    _FB_KEY = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'serviceAccountKey.json')
    if os.path.exists(_FB_KEY) and not firebase_admin._apps:
        firebase_admin.initialize_app(fb_creds.Certificate(_FB_KEY))
        FIREBASE_ADMIN = True
    else:
        FIREBASE_ADMIN = False
except ImportError:
    FIREBASE_ADMIN = False

app = Flask(__name__)
CORS(app, origins="*")

# ── Paths ──────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
HTML_DIR   = os.path.join(BASE_DIR, '..')
TOKEN_PATH = os.path.join(BASE_DIR, 'token.pickle')
CREDS_PATH = os.path.join(BASE_DIR, 'credentials.json')
DB_PATH    = os.path.join(BASE_DIR, 'users.db')

# ── Config ─────────────────────────────────────────────────────────
SCOPES     = ['https://www.googleapis.com/auth/drive.readonly']
SECRET_KEY = os.environ.get('SECRET_KEY', 'dsa-tracker-change-in-production')
serializer = URLSafeTimedSerializer(SECRET_KEY)

# stripe.api_key is set dynamically in routes
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
COURSE_PRICE_AMOUNT = int(os.environ.get('COURSE_PRICE_AMOUNT', 199900)) # Default 1999.00 INR (in paise)
COURSE_PRICE_CURRENCY = os.environ.get('COURSE_PRICE_CURRENCY', 'inr')

_service   = None



# ── Database ───────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


init_db()   # runs on startup (works with gunicorn too)


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
    if not auth_header.startswith('Bearer '):
        return jsonify({'error': 'No token provided'}), 401

    uid = 'anonymous'
    if FIREBASE_ADMIN:
        try:
            id_token = auth_header[7:]
            decoded = fb_auth.verify_id_token(id_token)
            uid = decoded['uid']
        except Exception:
            return jsonify({'error': 'Invalid or expired token'}), 401
    else:
        # If Firebase Admin isn't setup, we use the token itself as UID for simple local persistence mapping.
        uid = auth_header[7:]

    conn = get_db()
    
    if request.method == 'GET':
        row = conn.execute('SELECT state_json, is_paid FROM progress WHERE uid = ?', (uid,)).fetchone()
        conn.close()
        if row:
            return jsonify({'state': json.loads(row['state_json']), 'is_paid': bool(row['is_paid'])}), 200
        return jsonify({'state': {}, 'is_paid': False}), 200

    if request.method == 'POST':
        state_data = request.json.get('state', {})
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
    if not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json or {}
    coupon_code = data.get('code', '').upper().strip()
    uid = data.get('uid', 'anonymous')

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
@app.route('/api/checkout', methods=['POST'])
def create_checkout_session():
    stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Unauthorized'}), 401
    
    uid = 'anonymous'
    if FIREBASE_ADMIN:
        try:
            id_token = auth_header[7:]
            decoded = fb_auth.verify_id_token(id_token)
            uid = decoded['uid']
        except Exception:
            return jsonify({'error': 'Invalid token'}), 401
    else:
        data = request.json or {}
        uid = data.get('uid', 'anonymous')

    domain_url = request.headers.get('Origin', 'http://localhost:5000')

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': COURSE_PRICE_CURRENCY,
                    'product_data': {
                        'name': 'DSA Course Tracker Premium Access',
                    },
                    'unit_amount': COURSE_PRICE_AMOUNT,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=domain_url + '?payment_success=true',
            cancel_url=domain_url + '?payment_cancelled=true',
            client_reference_id=uid,
            allow_promotion_codes=True
        )
        return jsonify({'checkout_url': session.url}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/webhook/stripe', methods=['POST'])
def stripe_webhook():
    stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        return 'Invalid signature', 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        uid = session.get('client_reference_id')
        if uid:
            conn = get_db()
            conn.execute('''
                INSERT INTO progress (uid, state_json, is_paid)
                VALUES (?, '{}', 1)
                ON CONFLICT(uid) DO UPDATE SET is_paid = 1
            ''', (uid,))
            conn.commit()
            conn.close()

    return jsonify({'status': 'success'}), 200


# ── Page routes ────────────────────────────────────────────────────
@app.route('/')
def landing():
    return send_file(os.path.join(HTML_DIR, 'index.html'))

@app.route('/auth')
def auth_page():
    return send_file(os.path.join(HTML_DIR, 'auth.html'))

@app.route('/dashboard')
def dashboard():
    return send_file(os.path.join(HTML_DIR, 'dsa_tracker.html'))

@app.route('/firebase-config.js')
def firebase_config_js():
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
    js = (
        '// Auto-generated by Flask from environment variables
'
        f'const firebaseConfig = {json.dumps(cfg, indent=2)};
'
        f'const APP_CONFIG = {{ rootFolder: "{root_folder}" }};
'
    )
    return Response(js, mimetype='application/javascript')


# ── Google Drive API ───────────────────────────────────────────────
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
    stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
    # Verify auth token and check explicitly if paid 
    auth_token = request.args.get('token')
    is_paid = False
    
    if not auth_token:
        # Also try header for completeness, though Video tags use src=... url params
        auth_hdr = request.headers.get('Authorization','')
        if auth_hdr.startswith('Bearer '):
            auth_token = auth_hdr[7:]

    if auth_token:
        # decode uid
        try:
            if FIREBASE_ADMIN:
                decoded = fb_auth.verify_id_token(auth_token)
                uid = decoded['uid']
            else:
                uid = auth_token
            # check db
            conn = get_db()
            row = conn.execute('SELECT is_paid FROM progress WHERE uid = ?', (uid,)).fetchone()
            conn.close()
            if row and row['is_paid']:
                is_paid = True
        except:
            pass

    if not is_paid:
        # Instead of 402, returning a 403 or sending an empty chunk blocks it properly
        return jsonify({'error': 'Payment required to view video.'}), 402

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
    app.run(debug=False, port=port, host='0.0.0.0')
