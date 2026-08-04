import os
import numpy as np
from flask import Flask, request
from flask_socketio import SocketIO, join_room, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
# gevent აუცილებელია Railway-ზე SocketIO-ს სტაბილური მუშაობისთვის
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

word_vectors = {}
# დროებითი სამიზნე სიტყვა ტესტირებისთვის (თუ ოთახებზე გაქვს მიბმული, შეგიძლია შენი ლოგიკა დააბრუნო)
CURRENT_TARGET_WORD = "მგელი" 

def load_vectors():
    # 🔴 აქ შევცვალეთ vectors.txt -> vectors.vec
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
    
    # სადიაგნოსტიკო ლოგი - გამოჩნდება Railway-ს ლოგებში
    found_w1 = "მოიძებნა" if w1 in word_vectors else "ვერ მოიძებნა"
    found_w2 = "მოიძებნა" if w2 in word_vectors else "ვერ მოიძებნა"
    print(f"🔍 ვეძებთ: '{w1}' -> {found_w1} | სამიზნე: '{w2}' -> {found_w2}")
    
    if w1 not in word_vectors or w2 not in word_vectors:
        return 0.0
        
    v1 = word_vectors[w1]
    v2 = word_vectors[w2]
    
    # Cosine similarity-ს გამოთვლა (ვექტორები უკვე ნორმალიზებულია load_vectors-ში)
    similarity = np.dot(v1, v2)
    
    # ვაკონვერტირებთ 0-100 შკალაზე
    score = max(0.0, float(similarity) * 100)
    return round(score, 2)

@app.route('/')
def index():
    return "Kontekst.ge სერვერი ჩართულია და მუშაობს!"

@socketio.on('join_room')
def handle_join_room(data):
    room = data.get('room')
    if room:
        join_room(room)
        print(f"👤 მომხმარებელი შეუერთდა ოთახს: {room}")

@socketio.on('guess_word')
def handle_guess(data):
    room = data.get('room')
    word = data.get('word', '')
    username = data.get('username', 'მოთამაშე')
    
    # ვითვლით მსგავსებას შეყვანილ სიტყვასა და სამიზნე სიტყვას შორის
    score = get_similarity(word, CURRENT_TARGET_WORD)
    
    response = {
        'username': username,
        'word': word,
        'score': score
    }
    
    # ვაგზავნით შედეგს კონკრეტულ ოთახში მყოფ ყველა მოთამაშესთან
    if room:
        emit('guess_result', response, to=room)
    else:
        emit('guess_result', response)

if __name__ == '__main__':
    # Railway იყენებს PORT ცვლადს, ამიტომ მისი წაკითხვა აუცილებელია
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
