import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import re

# Config - Gemini API
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyAYR-G7nZz3D4YReB1tlq3YeSye1KN-wNY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_BASE_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

app = Flask(__name__)
CORS(app)

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


def build_prompt(user_text: str, tone: str | None) -> str:
    tone_text = ""
    if tone == "poetic":
        tone_text = "\nMake the tone more poetic and elaborate, but do not use ** ** markers."
    elif tone == "concise":
        tone_text = "\nMake the phrasing concise and practical, while retaining medieval flavor, but do not use ** ** markers."

    prompt_lines = [f"SYSTEM: {SYSTEM_PROMPT}{tone_text}\n\n"]
    for m, f in FEW_SHOT:
        prompt_lines.append(f"Modern: {m}\nMedieval: {f}\n\n")
    prompt_lines.append(f"Modern: {user_text}\nMedieval:")
    return "".join(prompt_lines)


@app.route("/api/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok", "model": GEMINI_MODEL})


@app.route('/api/translate', methods=['POST'])
def translate():
    data = request.get_json(force=True) or {}
    user_text = (data.get('text') or '').strip()
    tone = (data.get('tone') or '').strip().lower() or None

    if not user_text:
        return jsonify({'error': 'No text provided'}), 400

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

# Vercel serverless function handler
def handler(request):
    return app(request.environ, request.start_response)
