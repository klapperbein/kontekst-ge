import os
import random
import string
import time
import requests
import numpy as np
from flask import Flask, request, render_template
from flask_socketio import SocketIO, join_room as sio_join_room, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

word_vectors = {}
MAX_ATTEMPTS = 30

rooms = {}

VECTOR_DIR = "/data" if os.path.exists("/data") else "."
VECTOR_PATH = os.path.join(VECTOR_DIR, "vectors.vec")
NOUNS_PATH = os.path.join(VECTOR_DIR, "nouns.txt")

# ⚠️ ჩასვით აქ თქვენი Hugging Face-ის direct download ლინკები
DOWNLOAD_URL = "https://huggingface.co/datasets/klapperbein/georgian-vectors/resolve/main/vectors.vec"
NOUNS_DOWNLOAD_URL = "https://huggingface.co/datasets/klapperbein/georgian-vectors/resolve/main/nouns.txt"


def download_file_if_needed(path, url, label):
    if os.path.exists(path) and os.path.getsize(path) > 100:
        print(f"✅ {label} უკვე არსებობს: {path} — ჩამოტვირთვა არ სჭირდება.")
        return

    print(f"⬇️ ვწერთ {label}-ს {url}-დან...")
    try:
        with requests.get(url, stream=True, timeout=600) as r:
            r.raise_for_status()
            total = 0
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    total += len(chunk)
            print(f"✅ {label} ჩამოტვირთვა დასრულდა: {total / (1024*1024):.2f} MB")
    except Exception as e:
        print(f"❌ {label}-ის ჩამოტვირთვა ჩავარდა: {e}")


def download_vectors_if_needed():
    download_file_if_needed(VECTOR_PATH, DOWNLOAD_URL, "ვექტორების ფაილი")


def download_nouns_if_needed():
    download_file_if_needed(NOUNS_PATH, NOUNS_DOWNLOAD_URL, "არსებითი სახელების სია")


def load_nouns():
    if not os.path.exists(NOUNS_PATH):
        print("⚠️ nouns.txt ვერ მოიძებნა — გამოვიყენებთ ყველა სიტყვას (POS ფილტრის გარეშე).")
        return None
    with open(NOUNS_PATH, "r", encoding="utf-8") as f:
        return {line.strip().lower() for line in f if line.strip()}


def load_vectors():
    if not os.path.exists(VECTOR_PATH):
        print(f"⚠️ გაფრთხილება: {VECTOR_PATH} ვერ მოიძებნა!")
        return

    print("🚀 იტვირთება ქართული ენის ოპტიმიზებული მოდელი...")
    try:
        with open(VECTOR_PATH, "r", encoding="utf-8") as f:
            first_line = f.readline()
            for line in f:
                parts = line.rstrip().split(" ")
                if len(parts) > 1:
                    word = parts[0].strip().lower()
                    vector = np.array([float(x) for x in parts[1:]], dtype=np.float32)
                    norm = np.linalg.norm(vector)
                    if norm > 0:
                        word_vectors[word] = vector / norm
        print(f"✅ მოდელი წარმატებით ჩაიტვირთა! სულ დაემატა: {len(word_vectors)} სიტყვა.")
    except Exception as e:
        print(f"❌ შეცდომა მოდელის ჩატვირთვისას: {e}")


download_vectors_if_needed()
download_nouns_if_needed()
load_vectors()
NOUN_SET = load_nouns()  # None თუ nouns.txt ვერ ჩამოიტვირთა

# ==================== სამიზნე სიტყვების ავტომატური გენერაცია ====================
# ვირჩევთ სიტყვებს პირდაპირ ჩატვირთული ვექტორებიდან. ვინაიდან ფაილი
# სიხშირის მიხედვითაა დალაგებული, ჯერ ვტოვებთ ყველაზე ხშირ სიტყვებს,
# შემდეგ ვირჩევთ მხოლოდ სუფთა ქართულ, საკმარისი სიგრძის სიტყვებს,
# რომლებიც ასევე NOUN_SET-შიც მოიძებნება (ანუ ნამდვილად არსებითი სახელია).

TARGET_POOL_SIZE = 500     # რამდენი სამიზნე სიტყვა გვინდა სულ
SKIP_TOP_N = 300           # რამდენი ყველაზე ხშირი სიტყვა გამოვტოვოთ
MIN_WORD_LENGTH = 3        # მინიმალური სიგრძე ასოებში


def is_georgian_word(word):
    if not word:
        return False
    return all('\u10A0' <= ch <= '\u10FF' for ch in word)


def build_target_word_pool():
    pool = []
    for i, word in enumerate(word_vectors.keys()):
        if i < SKIP_TOP_N:
            continue
        if len(word) < MIN_WORD_LENGTH:
            continue
        if not is_georgian_word(word):
            continue
        if NOUN_SET is not None and word not in NOUN_SET:
            continue
        pool.append(word)
        if len(pool) >= TARGET_POOL_SIZE:
            break
    return pool


VALID_TARGET_WORDS = build_target_word_pool()
print(f"🎯 სამიზნე სიტყვების პული აშენდა: {len(VALID_TARGET_WORDS)} სიტყვა "
      f"({'POS ფილტრით' if NOUN_SET is not None else 'POS ფილტრის გარეშე'}).")

if not VALID_TARGET_WORDS:
    print("⚠️ პული ცარიელია! ვიყენებთ fallback-ს.")
    VALID_TARGET_WORDS = ["მგელი"] if "მგელი" in word_vectors else list(word_vectors.keys())[:1]
# ================================================================================


# ==================== Gemini AI-ს დახმარებით სამიზნე სიტყვის არჩევა ====================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-flash-latest"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def ask_gemini_for_noun():
    if not GEMINI_API_KEY:
        return None

    prompt = (
        "დამისახელე ერთი ჩვეულებრივი, კონკრეტული ქართული არსებითი სახელი "
        "(არა საკუთარი სახელი, არა აბსტრაქტული ცნება, არა ზმნა). "
        "უპასუხე მხოლოდ ერთი სიტყვით, ქართული ანბანით, "
        "პუნქტუაციის, ახსნის ან სხვა ტექსტის გარეშე."
    )

    try:
        resp = None
        resp = requests.post(
            GEMINI_URL,
            params={"key": GEMINI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 1.2,
                    "maxOutputTokens": 50,
                    "thinkingConfig": {"thinkingBudget": 0},
                },
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            print(f"⚠️ Gemini-მ ცარიელი candidates დააბრუნა: {data}")
            return None
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            print(f"⚠️ Gemini-ის პასუხს parts არ ჰქონდა (finishReason: "
                  f"{candidates[0].get('finishReason')}): {data}")
            return None
        text = parts[0].get("text", "")
        word = text.strip().split()[0].strip(".,!?\"'()«»").lower() if text.strip() else None
        return word
    except requests.exceptions.HTTPError as e:
        if resp is not None and resp.status_code == 429:
            print("⚠️ Gemini rate limit ამოწურულია (429) — ვბრუნდებით fallback-ზე.")
        else:
            print(f"⚠️ Gemini-სთან დაკავშირება ჩავარდა: {e}")
        return None
    except Exception as e:
        print(f"⚠️ Gemini-სთან დაკავშირება ჩავარდა: {e}")
        return None
# ================================================================================


def pick_target_word():
    # ჯერ ვცდით Gemini-სგან სიტყვის მიღებას (თუ API key დაყენებულია)
    for attempt in range(3):
        word = ask_gemini_for_noun()
        if word and word in word_vectors:
            print(f"🤖 Gemini-მ აირჩია სამიზნე სიტყვა: {word}")
            return word
        if attempt < 2:
            time.sleep(1.5)  # ვიცდით ცოტას, რომ rate limit არ დავარღვიოთ

    # fallback: თუ Gemini არ არის კონფიგურირებული, ან ვერცერთხელ
    # ვერ დააბრუნა ისეთი სიტყვა, რომელიც ვექტორებში მოიძებნება
    print("↩️ ვბრუნდებით ლოკალურ სიტყვების პულზე (Gemini ვერ დაგვეხმარა).")
    return random.choice(VALID_TARGET_WORDS)


def get_similarity(word1, word2):
    w1 = word1.strip().lower()
    w2 = word2.strip().lower()

    if w1 not in word_vectors or w2 not in word_vectors:
        return 0.0

    v1 = word_vectors[w1]
    v2 = word_vectors[w2]
    similarity = np.dot(v1, v2)
    score = max(0.0, float(similarity) * 100)
    return round(score, 2)


def generate_room_id():
    while True:
        room_id = ''.join(random.choices(string.digits, k=4))
        if room_id not in rooms:
            return room_id


@app.route('/')
def index():
    template_path = os.path.join(app.root_path, 'templates', 'index.html')
    if os.path.exists(template_path):
        return render_template('index.html')
    else:
        return "Kontekst.ge სერვერი ჩართულია და მუშაობს! (HTML ფაილი 'templates/index.html' ვერ მოიძებნა)"


@socketio.on('connect')
def handle_connect():
    print(f"✅ ახალი client დაუკავშირდა: {request.sid}")


@socketio.on('disconnect')
def handle_disconnect():
    print(f"❌ client გამოეთიშა: {request.sid}")


@socketio.on('create_room')
def handle_create_room(data):
    username = data.get('username', 'მოთამაშე 1')
    room_id = generate_room_id()
    target_word = pick_target_word()

    rooms[room_id] = {
        'target_word': target_word,
        'history': [],
        'is_over': False,
    }

    sio_join_room(room_id)
    print(f"🆕 ოთახი შეიქმნა: {room_id} მომხმარებლის მიერ: {username} | სამიზნე: {target_word}")
    emit('room_created', {'room_id': room_id})


@socketio.on('join_room')
def handle_join_room(data):
    room_id = data.get('room_id')
    username = data.get('username', 'მოთამაშე 2')

    if not room_id or room_id not in rooms:
        emit('error_message', {'error': 'ოთახი ვერ მოიძებნა. გადაამოწმეთ PIN კოდი.'})
        return

    sio_join_room(room_id)
    print(f"👤 მომხმარებელი '{username}' შეუერთდა ოთახს: {room_id}")

    room = rooms[room_id]
    emit('player_joined', {
        'room_id': room_id,
        'history': room['history'],
    })


@socketio.on('make_guess')
def handle_make_guess(data):
    room_id = data.get('room_id')
    word = data.get('word', '')
    username = data.get('username', 'მოთამაშე')

    if not room_id or room_id not in rooms:
        emit('error_message', {'error': 'ოთახი ვერ მოიძებნა.'})
        return

    room = rooms[room_id]

    if room['is_over']:
        emit('error_message', {'error': 'თამაში უკვე დასრულებულია.'})
        return

    target_word = room['target_word']
    score = get_similarity(word, target_word)
    is_correct = (word.strip().lower() == target_word.strip().lower())

    room['history'].append({
        'player': username,
        'word': word,
        'score': score,
    })
    room['history'].sort(key=lambda x: x['score'], reverse=True)

    is_over = is_correct or len(room['history']) >= MAX_ATTEMPTS
    room['is_over'] = is_over

    response = {
        'history': room['history'],
        'is_over': is_over,
        'is_correct': is_correct,
        'latest_player': username,
        'target_word': target_word if is_over else None,
    }

    emit('room_update', response, to=room_id)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
