import os
import numpy as np
from flask import Flask, render_template
from flask_socketio import SocketIO, join_room, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

word_vectors = {}
CURRENT_TARGET_WORD = "მგელი" 
VECTOR_FILE = "vectors.vec"

def load_vectors():
    if not os.path.exists(VECTOR_FILE):
        print(f"⚠️ {VECTOR_FILE} ფაილი ვერ მოიძებნა!")
        return

    with open(VECTOR_FILE, "r", encoding="utf-8") as f:
        next(f) # პირველი, საინფორმაციო ხაზის გამოტოვება
        for line in f:
            parts = line.rstrip().split(" ")
            if len(parts) > 1:
                word = parts[0].strip().lower()
                vector = np.array(parts[1:], dtype=np.float32)
                norm = np.linalg.norm(vector)
                if norm > 0:
                    word_vectors[word] = vector / norm
    print(f"✅ მოდელი ჩაიტვირთა: {len(word_vectors)} სიტყვა.")

load_vectors()

def get_similarity(w1, w2):
    w1, w2 = w1.strip().lower(), w2.strip().lower()
    
    if w1 not in word_vectors or w2 not in word_vectors:
        return 0.0
        
    similarity = np.dot(word_vectors[w1], word_vectors[w2])
    return round(max(0.0, float(similarity) * 100), 2)

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('join_room')
def handle_join_room(data):
    if room := data.get('room'):
        join_room(room)

@socketio.on('guess_word')
def handle_guess(data):
    room = data.get('room')
    word = data.get('word', '')
    username = data.get('username', 'მოთამაშე')
    
    score = get_similarity(word, CURRENT_TARGET_WORD)
    response = {'username': username, 'word': word, 'score': score}
    
    if room:
        emit('guess_result', response, to=room)
    else:
        emit('guess_result', response)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
