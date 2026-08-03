import os
import math
import random
import numpy as np
from flask import Flask, render_template
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret-key-kontekst-ge'
socketio = SocketIO(app, cors_allowed_origins="*")

# FastText მოდელის ჩატვირთვა
word_vectors = {}

def load_vectors():
    vector_file = "cc.ka.300.small.vec"
    if not os.path.exists(vector_file):
        print(f"⚠️ გაფრთხილება: {vector_file} ვერ მოიძებნა!")
        return

    print("🚀 ტვირთება ქართული ენის ოპტიმიზებული მოდელი...")
    with open(vector_file, "r", encoding="utf-8") as f:
        first_line = f.readline()
        for line in f:
            parts = line.rstrip().split(" ")
            word = parts[0]
            vector = np.array([float(x) for x in parts[1:]], dtype=np.float32)
            norm = np.linalg.norm(vector)
            if norm > 0:
                word_vectors[word] = vector / norm
    print("✅ მოდელი წარმატებით ჩაიტვირთა!")

load_vectors()

TARGET_WORDS = [
    "სახლი", "კომპიუტერი", "წიგნი", "მანქანა", "ტელეფონი", "საათი", "კალამი", "მაგიდა", "სკამი", "ოთახი",
    "ფანჯარა", "კარი", "ჩანთა", "ფული", "სარკე", "საწოლი", "კარადა", "ხალიჩა", "ლამპა", "ტელევიზორი",
    "მზე", "წყალი", "ზღვა", "მთა", "ტყე", "ქარი", "წვიმა", "ცეცხლი", "მიწა", "ვარსკვლავი",
    "ქალაქი", "სკოლა", "ქუჩა", "პარკი", "მაღაზია", "თეატრი", "მუზეუმი", "ხიდი", "შენობა", "ბინა",
    "ავტომობილი", "ავტობუსი", "მატარებელი", "თვითმფრინავი", "გემი", "ველოსიპედი", "რაკეტა", "დრონი",
    "პური", "ყველი", "ღვინო", "ყავა", "ჩაი", "ხორცი", "ვაშლი", "შოკოლადი", "სადილი", "საუზმე",
    "ძაღლი", "კატა", "ცხენი", "ფრინველი", "დათვი", "მგელი", "არწივი", "ლომი", "ვეფხვი",
    "ადამიანი", "კაცი", "ქალი", "ბავშვი", "ბიჭი", "გოგო", "ექიმი", "მასწავლებელი", "ინჟინერი", "მეგობარი",
    "სიყვარული", "ბედნიერება", "სიცოცხლე", "ოცნება", "იმედი", "სიმშვიდე", "თავისუფლება", "დრო", "ისტორია",
    "ფეხბურთი", "კალათბურთი", "ჭადრაკი", "ცურვა", "სირბილი", "კინო", "ფილმი", "მუსიკა", "ცეკვა"
]

rooms = {}

def get_similarity(w1, w2):
    if w1 not in word_vectors or w2 not in word_vectors:
        return 0.0
    v1 = word_vectors[w1]
    v2 = word_vectors[w2]
    sim = np.dot(v1, v2)
    score = max(0.0, float(sim)) * 100
    return round(score, 1)

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('create_room')
def handle_create_room(data):
    username = data.get('username', 'მოთამაშე 1')
    room_id = str(random.randint(1000, 9999))
    target = random.choice(TARGET_WORDS)
    
    rooms[room_id] = {
        'target_word': target,
        'guesses': [],
        'players': [username],
        'is_over': False,
        'max_guesses': 30
    }
    
    join_room(room_id)
    emit('room_created', {
        'room_id': room_id,
        'max_guesses': 30,
        'guesses_count': 0
    })

@socketio.on('join_room')
def handle_join_room(data):
    room_id = data.get('room_id')
    username = data.get('username', 'მოთამაშე 2')

    if not room_id or room_id not in rooms:
        emit('error_message', {'error': 'ოთახი არ მოიძებნა! შეამოწმეთ PIN კოდი.'})
        return

    room = rooms[room_id]
    if username not in room['players']:
        room['players'].append(username)

    join_room(room_id)
    emit('player_joined', {
        'room_id': room_id,
        'history': room['guesses'],
        'guesses_count': len(room['guesses']),
        'max_guesses': room['max_guesses'],
        'is_over': room['is_over']
    })

@socketio.on('make_guess')
def handle_make_guess(data):
    room_id = data.get('room_id')
    username = data.get('username')
    word = data.get('word', '').strip().lower()

    if not room_id or room_id not in rooms:
        return

    room = rooms[room_id]
    if room['is_over']:
        return

    target = room['target_word']
    score = get_similarity(word, target)
    is_correct = (word == target)

    guess_entry = {
        'player': username,
        'word': word,
        'score': score
    }
    
    room['guesses'].append(guess_entry)
    
    # 🌟 მუდმივად ვალაგებთ ქულის კლებადობით (ყველაზე მაღალი პროცენტი მიდის თავში)
    room['guesses'] = sorted(room['guesses'], key=lambda x: x['score'], reverse=True)
    
    guesses_count = len(room['guesses'])

    if is_correct or guesses_count >= room['max_guesses']:
        room['is_over'] = True

    emit('room_update', {
        'history': room['guesses'],
        'guesses_count': guesses_count,
        'max_guesses': room['max_guesses'],
        'is_over': room['is_over'],
        'is_correct': is_correct,
        'target_word': target if room['is_over'] else None,
        'latest_word': word,
        'latest_player': username
    }, to=room_id)

if __name__ == '__main__':
    socketio.run(app, debug=True, port=5001)
