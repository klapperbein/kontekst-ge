import os
import random
import string
import numpy as np
from flask import Flask, request, render_template
from flask_socketio import SocketIO, join_room as sio_join_room, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'

# gevent აუცილებელია Railway-ზე SocketIO-ს სტაბილური მუშაობისთვის
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

word_vectors = {}
CURRENT_TARGET_WORD = "მგელი"

MAX_ATTEMPTS = 30  # რამდენი მცდელობის შემდეგ დასრულდეს თამაში

# ოთახების მდგომარეობა: room_id -> {target_word, history, is_over}
rooms = {}


def load_vectors():
    vector_file = "vectors.vec"

    if not os.path.exists(vector_file):
        print(f"⚠️ გაფრთხილება: {vector_file} ვერ მოიძებნა ძირ დირექტორიაში!")
        return
    print("🚀 იტვირთება ქართული ენის ოპტიმიზებული მოდელი...")
    try:
        with open(vector_file, "r", encoding="utf-8") as f:
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


# ვტვირთავთ მოდელს სერვერის ჩართვისას
load_vectors()


def get_similarity(word1, word2):
    w1 = word1.strip().lower()
    w2 = word2.strip().lower()

    found_w1 = "მოიძებნა" if w1 in word_vectors else "ვერ მოიძებნა"
    found_w2 = "მოიძებნა" if w2 in word_vectors else "ვერ მოიძებნა"
    print(f"🔍 ვეძებთ: '{w1}' -> {found_w1} | სამიზნე: '{w2}' -> {found_w2}")

    if w1 not in word_vectors or w2 not in word_vectors:
        return 0.0

    v1 = word_vectors[w1]
    v2 = word_vectors[w2]

    similarity = np.dot(v1, v2)

    score = max(0.0, float(similarity) * 100)
    return round(score, 2)


def generate_room_id():
    """ქმნის უნიკალურ 4-ციფრიან PIN კოდს ოთახისთვის."""
    while True:
        room_id = ''.join(random.choices(string.digits, k=4))
        if room_id not in rooms:
            return room_id


@app.route('/')
def index():
    # absolute path გამოიყენება, რადგან os.path.exists
    # მიმდინარე working directory-ს ეყრდნობა და Railway-ზე
    # შეცდომით 'ვერ მოიძებნა' შეიძლება დააბრუნოს
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

    rooms[room_id] = {
        'target_word': CURRENT_TARGET_WORD,
        'history': [],
        'is_over': False,
    }

    sio_join_room(room_id)
    print(f"🆕 ოთახი შეიქმნა: {room_id} მომხმარებლის მიერ: {username}")

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
    # ისტორია დალაგებული ქულის კლებადობით (ყველაზე მაღალი ზემოთ)
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
