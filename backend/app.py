import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import re
from datetime import datetime, timedelta
from collections import defaultdict
import hashlib

# Config - Gemini API
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is required")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_BASE_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

# Security Config
API_SECRET = os.environ.get("API_SECRET", "medieval-translator-2025")  # Change this!
RATE_LIMIT_PER_MINUTE = 10  # Max requests per minute per IP
RATE_LIMIT_PER_HOUR = 100   # Max requests per hour per IP

app = Flask(__name__)
CORS(app)

# Rate limiting storage (in production, use Redis)
rate_limit_storage = defaultdict(list)
# Session token storage (in production, use Redis with expiration)
session_tokens = defaultdict(datetime)

def generate_session_token():
    """Generate a unique session token"""
    import secrets
    return secrets.token_urlsafe(32)

def validate_session_token(token):
    """Validate if session token is valid and not expired"""
    if not token or token not in session_tokens:
        return False
    
    # Check if token is expired (30 minutes)
    token_time = session_tokens[token]
    if datetime.now() - token_time > timedelta(minutes=30):
        del session_tokens[token]  # Clean up expired token
        return False
    
    return True

def get_client_ip():
    """Get the real client IP address"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return request.remote_addr

def is_rate_limited(ip):
    """Check if IP is rate limited"""
    now = datetime.now()
    minute_ago = now - timedelta(minutes=1)
    hour_ago = now - timedelta(hours=1)
    
    # Clean old entries
    rate_limit_storage[ip] = [
        timestamp for timestamp in rate_limit_storage[ip]
        if timestamp > hour_ago
    ]
    
    # Count recent requests
    recent_requests = rate_limit_storage[ip]
    requests_last_minute = sum(1 for req in recent_requests if req > minute_ago)
    requests_last_hour = len(recent_requests)
    
    # Check limits
    if requests_last_minute >= RATE_LIMIT_PER_MINUTE:
        return True, f"Rate limit exceeded: {requests_last_minute}/{RATE_LIMIT_PER_MINUTE} per minute"
    if requests_last_hour >= RATE_LIMIT_PER_HOUR:
        return True, f"Rate limit exceeded: {requests_last_hour}/{RATE_LIMIT_PER_HOUR} per hour"
    
    return False, None

def record_request(ip):
    """Record a request for rate limiting"""
    rate_limit_storage[ip].append(datetime.now())

def verify_request_authenticity():
    """Enhanced security checks including referrer validation"""
    # Check for required headers that browsers send
    required_headers = ['User-Agent']
    for header in required_headers:
        if not request.headers.get(header):
            return False, f"Missing {header} header"
    
    # Check for suspicious user agents (even spoofed ones)
    user_agent = request.headers.get('User-Agent', '').lower()
    suspicious_agents = ['curl', 'wget', 'python-requests', 'postman', 'insomnia']
    for agent in suspicious_agents:
        if agent in user_agent:
            return False, f"Suspicious user agent: {agent}"
    
    # CSRF Protection: Check referrer/origin - BOTH must be valid
    referrer = request.headers.get('Referer', '')  # Note: HTTP spec has this typo
    origin = request.headers.get('Origin', '')
    
    # Allow requests from your legitimate domains
    allowed_domains = [
        'https://medieval-translator-app.vercel.app',
        'https://medieval-translator-app-joeldlimas-projects.vercel.app', 
        'https://medieval-translator-app-git-main-joeldlimas-projects.vercel.app',
        'http://localhost:3000',  # For local development
        'http://127.0.0.1:5000',  # For local Flask development
    ]
    
    # Check if request comes from an allowed domain
    valid_referrer = any(referrer.startswith(domain) for domain in allowed_domains) if referrer else False
    valid_origin = any(origin == domain for domain in allowed_domains) if origin else False
    
    # STRICTER: Require BOTH referrer AND origin, or reject
    if not referrer or not origin:
        return False, "Missing required security headers (Referer and Origin required)"
    
    if not valid_referrer:
        return False, f"Invalid referrer: {referrer}"
    
    if not valid_origin:
        return False, f"Invalid origin: {origin}"
    
    # Additional browser-specific checks
    if not request.headers.get('Accept'):
        return False, "Missing Accept header"
    
    # Check for browser-specific security headers
    sec_fetch_site = request.headers.get('Sec-Fetch-Site')
    if sec_fetch_site and sec_fetch_site not in ['same-origin', 'same-site']:
        return False, f"Invalid Sec-Fetch-Site: {sec_fetch_site}"
    
    # Check for API secret in headers (for legitimate API usage)
    api_secret = request.headers.get('X-API-Secret')
    if api_secret == API_SECRET:
        return True, "Valid API secret provided"
    
    return True, "Request appears legitimate"

SYSTEM_PROMPT = (
    "You are a medieval English scribe and storyteller in a fantasy realm. "
    "Rewrite the given modern English text into a faux medieval / fantasy style. "
    "Keep the meaning intact, use archaic vocabulary (thee, thou, hath, doth, morrow, yon), "
    "use slightly poetic phrasing, and add one tasteful flourish or archaic idiom where appropriate. "
    "Do not hallucinate facts or add new events; preserve named entities unless asked to embellish. "
    "Do not use ** ** markers or parenthetical comments in your response. Provide only the clean medieval text."
)

FEW_SHOT = [
    # BASIC GREETINGS & QUESTIONS
    ("Hello there.", "Hail, traveller."),
    ("How are you?", "How fare thee this day?"),
    ("What is your name?", "Pray, what be thy name?"),
    ("Where am I?", "Pray tell, wherefore art thou in these parts?"),
    ("Who are you?", "Who art thou, that cometh before me?"),
    ("Can you help me?", "Might thou lend me thine aid?"),
    ("What time is it?", "What hour doth the bells now toll?"),
    ("Where is the tavern?", "Whither lies yon tavern?"),
    ("I am hungry.", "Mine own belly doth rumble with hunger."),
    ("I need water.", "I am in dire need of a draught of water."),

    # TRAVEL & DIRECTIONS
    ("How far is the next village?", "How far hence lies the next village?"),
    ("Can you guide me to the castle?", "Couldst thou guide me unto the castle keep?"),
    ("The road is blocked.", "Yon road is barred to travellers."),
    ("Is it safe to travel at night?", "Be it safe to journey by moonlight?"),
    ("I am lost.", "I am sorely lost in these wild lands."),
    ("We must cross the river.", "We must needs ford yon river."),
    ("Where does this path lead?", "Whither doth this path wend?"),
    ("Do you know a shortcut?", "Dost thou ken a swifter way?"),

    # WARNINGS & COMMANDS
    ("Stop right there!", "Halt! Stand and deliver!"),
    ("You should leave immediately.", "Thou must away at once!"),
    ("Do not touch that.", "Lay not thy hand upon that."),
    ("This place is forbidden.", "These halls be forbidden to thee."),
    ("Stay out of trouble.", "Cause no mischief in these parts."),
    ("Watch your back.", "Keep thy wits about thee."),
    ("The forest is dangerous.", "Yon forest be full of peril."),
    ("The king is not to be disturbed.", "Disturb not the king in his hall."),
    ("Stay close to me.", "Bide close at mine own side."),

    # TAVERN & MARKET
    ("I would like some food.", "Bring me victuals, if thou wouldst be so kind."),
    ("Can I have a drink?", "Pray, might I have a draught?"),
    ("How much does this cost?", "What price dost thou ask for this?"),
    ("Do you sell swords?", "Dost thou deal in blades?"),
    ("I need a room for the night.", "Hast thou a chamber wherein I might lay mine head?"),
    ("The ale is strong here.", "Yon ale be stout indeed."),
    ("I will pay in gold.", "I shall pay thee in gold coin."),
    ("This bread is stale.", "This loaf be hard as an old helm."),

    # COMBAT & QUESTING
    ("Prepare yourself for battle!", "Ready thyself for the coming fray!"),
    ("We ride at dawn.", "We ride forth at the break of day."),
    ("Do you have a weapon?", "Hast thou a blade at thy side?"),
    ("The enemy approaches!", "The foe draweth nigh!"),
    ("We will fight to the last.", "We shall fight unto the last man."),
    ("Victory will be ours.", "Victory shall be ours this day."),
    ("The battle is lost.", "The field is lost to us."),
    ("You fight well.", "Thou dost wield thy blade with skill."),
    ("Your armor is impressive.", "Thy mail be most finely wrought."),

    # MISC DRAMA & NPC VIBES
    ("I heard strange noises last night.", "I heard strange clamour in the dark of night."),
    ("Have you heard the latest news?", "Hast thou heard the tidings of late?"),
    ("The harvest has been poor this year.", "The harvest be meagre in this year."),
    ("The roads are swarming with bandits.", "Bandits do haunt the roads these days."),
    ("This land was once peaceful.", "Once, this realm knew peace."),
    ("The old ruins are cursed.", "Yon ancient ruins be accursèd."),
    ("Legends say a dragon sleeps there.", "Tales do speak of a wyrm that slumbers there."),
    ("The gods watch over us.", "The gods keepeth watch o'er our fate."),
    ("May fortune smile upon you.", "May fortune's favour rest upon thee."),
]


def clean_response(text: str) -> str:
    """Clean up model response by removing markdown formatting and unwanted markers"""
    # Remove ** ** markers and content within them
    text = re.sub(r'\*\*.*?\*\*', '', text)
    # Remove parenthetical comments like (A tasteful flourish: ...)
    text = re.sub(r'\([^)]*flourish[^)]*\)', '', text, flags=re.IGNORECASE)
    # Remove any remaining markdown-style formatting
    text = re.sub(r'\*([^*]+)\*', r'\1', text)  # Remove *italics*
    text = re.sub(r'_([^_]+)_', r'\1', text)    # Remove _underline_
    # Clean up extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def sanitize_user_input(text: str) -> str:
    """Sanitize user input to prevent prompt injection attacks"""
    if not text:
        return text
    
    # Remove common prompt injection patterns
    dangerous_patterns = [
        r'ignore\s+previous\s+instructions?',
        r'ignore\s+above',
        r'forget\s+previous\s+instructions?',
        r'forget\s+above',
        r'system\s*:',
        r'assistant\s*:',
        r'human\s*:',
        r'user\s*:',
        r'prompt\s*:',
        r'instructions?\s*:',
        r'override',
        r'new\s+task',
        r'new\s+instruction',
        r'role\s*:',
        r'you\s+are\s+now',
        r'act\s+as',
        r'pretend\s+to\s+be',
        r'simulate',
        r'<\s*system\s*>',
        r'<\s*\/\s*system\s*>',
        r'<\s*prompt\s*>',
        r'<\s*\/\s*prompt\s*>',
    ]
    
    # Remove dangerous patterns (case insensitive)
    cleaned_text = text
    for pattern in dangerous_patterns:
        cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.IGNORECASE)
    
    # Limit length to prevent abuse
    if len(cleaned_text) > 500:
        cleaned_text = cleaned_text[:500]
    
    # Remove excessive newlines and clean whitespace
    cleaned_text = re.sub(r'\n\s*\n\s*\n+', '\n\n', cleaned_text)
    cleaned_text = cleaned_text.strip()
    
    return cleaned_text


def build_prompt(user_text: str, tone: str | None) -> str:
    # Sanitize user input first
    sanitized_text = sanitize_user_input(user_text)
    
    tone_text = ""
    if tone == "poetic":
        tone_text = "\nMake the tone more poetic and elaborate, but do not use ** ** markers."
    elif tone == "concise":
        tone_text = "\nMake the phrasing concise and practical, while retaining medieval flavor, but do not use ** ** markers."

    prompt_lines = [f"SYSTEM: {SYSTEM_PROMPT}{tone_text}\n\n"]
    for m, f in FEW_SHOT:
        prompt_lines.append(f"Modern: {m}\nMedieval: {f}\n\n")
    prompt_lines.append(f"Modern: {sanitized_text}\nMedieval:")
    return "".join(prompt_lines)


@app.route("/healthz", methods=["GET"])
@app.route("/api/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok", "model": GEMINI_MODEL, "security": "v2.0"})


@app.route("/session", methods=["GET"])
@app.route("/api/session", methods=["GET"])
def get_session():
    """Generate a session token for legitimate website usage"""
    # Basic checks to ensure request comes from the website
    referrer = request.headers.get('Referer', '')
    origin = request.headers.get('Origin', '')
    
    allowed_domains = [
        'https://medieval-translator-app.vercel.app',
        'https://medieval-translator-app-joeldlimas-projects.vercel.app', 
        'https://medieval-translator-app-git-main-joeldlimas-projects.vercel.app',
        'http://localhost:3000',
        'http://127.0.0.1:5000',
    ]
    
    valid_referrer = any(referrer.startswith(domain) for domain in allowed_domains)
    valid_origin = any(origin == domain for domain in allowed_domains)
    
    if not (valid_referrer or valid_origin):
        return jsonify({'error': 'Session tokens only available from the website'}), 403
    
    token = generate_session_token()
    session_tokens[token] = datetime.now()
    
    return jsonify({'token': token})


@app.route('/translate', methods=['POST'])
@app.route('/api/translate', methods=['POST'])
def translate():
    # Security: Rate limiting and authenticity checks
    client_ip = get_client_ip()
    limited, reason = is_rate_limited(client_ip)
    if limited:
        return jsonify({'error': reason}), 429
    record_request(client_ip)

    # Security: Check request authenticity (referrer/origin validation)
    authentic, auth_reason = verify_request_authenticity()
    if not authentic:
        return jsonify({'error': f'Request blocked: {auth_reason}'}), 403

    # Security: Validate session token - NO EXCEPTIONS
    data = request.get_json(force=True) or {}
    session_token = data.get('session_token') or request.headers.get('X-Session-Token')
    
    # MANDATORY session token - no bypasses allowed
    if not session_token:
        return jsonify({'error': 'Session token required - get one from /api/session'}), 401
    
    if not validate_session_token(session_token):
        return jsonify({'error': 'Invalid or expired session token - get a new one from /api/session'}), 401

    user_text = (data.get('text') or '').strip()
    tone = (data.get('tone') or '').strip().lower() or None

    if not user_text:
        return jsonify({'error': 'No text provided'}), 400
    if len(user_text) > 500:
        return jsonify({'error': 'Text too long. Please limit to 500 characters.'}), 400
    if not user_text or len(user_text.strip()) < 1:
        return jsonify({'error': 'Please provide valid text to translate'}), 400

    prompt = build_prompt(user_text, tone)

    try:
        # Use Gemini API to generate text
        headers = {
            'Content-Type': 'application/json'
        }
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ]
        }
        
        resp = requests.post(GEMINI_BASE_URL, headers=headers, json=payload, timeout=15)
        
        if resp.status_code != 200:
            return jsonify({'error': 'Gemini API call failed', 'details': resp.text}), 502
            
        response_data = resp.json()
        
        # Extract the generated text from Gemini response
        raw_output = response_data['candidates'][0]['content']['parts'][0]['text'].strip()
        
        # Clean the response to remove formatting issues
        cleaned_output = clean_response(raw_output)
        
        return jsonify({'result': cleaned_output})
        
    except requests.Timeout:
        return jsonify({'error': 'Gemini API timed out'}), 504
    except KeyError as e:
        return jsonify({'error': 'Unexpected Gemini API response format', 'details': str(e)}), 502
    except Exception as e:
        return jsonify({'error': 'Server error', 'details': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

# For Vercel
application = app
