from flask import Flask, render_template, request, redirect, jsonify, g
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)

# ------------------ PATH SETUP ------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
DB_FOLDER = os.path.join(BASE_DIR, "database")
DB_PATH = os.path.join(DB_FOLDER, "notes.db")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DB_FOLDER, exist_ok=True)

# ------------------ DATABASE ------------------
def init_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()

    # Notes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_text TEXT,
            corrected_text TEXT,
            created_at TEXT
        )
    """)

    # Timetable table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS timetable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT,
            task TEXT,
            reminder_time TEXT,
            repeat_daily INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=30)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db:
        db.close()


# ------------------ UTIL FUNCTIONS ------------------

def correct_note(text):
    text = text.strip()
    if not text:
        return ""

    text = text[0].upper() + text[1:]
    if not text.endswith((".", "!", "?")):
        text += "."

    replacements = {
        " i ": " I ",
        "java": "Java",
        "sql": "SQL",
        "python": "Python",
    }

    corrected = " " + text + " "
    for k, v in replacements.items():
        corrected = corrected.replace(k, v)

    return corrected.strip()


def analyze_learning(notes):
    topics = {
        "java": 0,
        "sql": 0,
        "arraylist": 0,
        "inheritance": 0
    }

    for note in notes:
        text = (note["raw_text"] or "") + " " + (note["corrected_text"] or "")
        text = text.lower()

        for topic in topics:
            if topic in text:
                topics[topic] += 1

    return topics


def generate_suggestions(analysis):
    suggestions = []

    if analysis["java"] > 0:
        suggestions.append("Focus on Java Collections next.")
    if analysis["arraylist"] > 0:
        suggestions.append("Learn HashMap after ArrayList.")
    if analysis["inheritance"] > 0:
        suggestions.append("Move to polymorphism.")

    if not suggestions:
        suggestions.append("Start with Java basics.")

    return suggestions


def get_smart_reminder_message(subject, task):
    if "java" in subject.lower():
        return f"Time for Java: {task}"
    if "sql" in subject.lower():
        return f"Practice SQL: {task}"
    return f"Start {subject}: {task}"


def update_missed_tasks():
    db = get_db()
    now = datetime.now().strftime("%H:%M")

    db.execute("""
        UPDATE timetable
        SET status = 'missed'
        WHERE status = 'pending' AND reminder_time < ?
    """, (now,))
    db.commit()


def ai_friend_response(msg):
    msg = msg.lower()

    if "learn" in msg:
        return "Focus on Java Collections and SQL joins."
    if "inheritance" in msg:
        return "Inheritance allows reuse of code from parent class."
    if "arraylist" in msg:
        return "ArrayList is dynamic array in Java."

    return "Keep learning step by step. You are improving."
def generate_ai_timetable_suggestions(notes, timetable):
    suggestions = []

    note_text = " ".join(
        ((note["raw_text"] or "") + " " + (note["corrected_text"] or ""))
        for note in notes
    ).lower()

    missed_tasks = [task for task in timetable if task["status"] == "missed"]

    if "inheritance" in note_text:
        suggestions.append("You studied inheritance. Add polymorphism to tomorrow's timetable.")

    if "arraylist" in note_text:
        suggestions.append("You studied ArrayList. Schedule HashMap practice next.")

    if "sql" not in note_text:
        suggestions.append("You are not practicing SQL enough. Add SQL session.")

    if len(missed_tasks) >= 2:
        suggestions.append("You missed multiple tasks. Reduce workload and stay consistent.")

    if not suggestions:
        suggestions.append("Maintain balance: Java + SQL + Revision.")

    return suggestions


def generate_auto_timetable(notes, timetable, start_time, end_time, session_count):
    note_text = " ".join(
        ((note["raw_text"] or "") + " " + (note["corrected_text"] or ""))
        for note in notes
    ).lower()

    missed_tasks = [task for task in timetable if task["status"] == "missed"]

    topics = []

    if "java" in note_text:
        topics.append(("Java", "Practice Collections"))
    else:
        topics.append(("Java", "Revise Java Basics"))

    if "arraylist" in note_text:
        topics.append(("Java", "Practice HashMap"))
    if "inheritance" in note_text:
        topics.append(("Java", "Learn Polymorphism"))

    if "sql" in note_text:
        topics.append(("SQL", "Practice Joins"))
    else:
        topics.append(("SQL", "Revise SQL Basics"))

    if missed_tasks:
        topics.append(("Revision", "Revise missed topics"))

    topics.append(("Revision", "Review old notes"))

    # remove duplicates while keeping order
    unique_topics = []
    seen = set()
    for subject, task in topics:
        key = (subject, task)
        if key not in seen:
            seen.add(key)
            unique_topics.append((subject, task))

    # limit to session count
    selected = unique_topics[:session_count]

    fmt = "%H:%M"
    start_dt = datetime.strptime(start_time, fmt)
    end_dt = datetime.strptime(end_time, fmt)

    total_minutes = int((end_dt - start_dt).total_seconds() / 60)
    if total_minutes <= 0 or session_count <= 0:
        return []

    slot_minutes = total_minutes // session_count
    if slot_minutes <= 0:
        return []

    generated = []
    current = start_dt

    for subject, task in selected:
        generated.append({
            "subject": subject,
            "task": task,
            "reminder_time": current.strftime("%H:%M")
        })
        current = current.replace(
            hour=(current.hour + (current.minute + slot_minutes) // 60) % 24,
            minute=(current.minute + slot_minutes) % 60
        )

    return generated

# ------------------ ROUTES ------------------
@app.route("/")
def home():
    db = get_db()

    update_missed_tasks()

    notes = db.execute("SELECT * FROM notes ORDER BY id DESC").fetchall()
    timetable = db.execute("SELECT * FROM timetable ORDER BY reminder_time").fetchall()

    analysis = analyze_learning(notes)
    suggestions = generate_suggestions(analysis)
    ai_timetable_suggestions = generate_ai_timetable_suggestions(notes, timetable)

    return render_template(
        "index.html",
        notes=notes,
        timetable=timetable,
        analysis=analysis,
        suggestions=suggestions,
        ai_timetable_suggestions=ai_timetable_suggestions,
        generated_plan=[]
    )
    @app.route("/generate-auto-timetable", methods=["POST"])
    def generate_auto_plan():
         db = get_db()

    notes = db.execute("SELECT * FROM notes ORDER BY id DESC").fetchall()
    timetable = db.execute("SELECT * FROM timetable ORDER BY reminder_time").fetchall()

    start_time = request.form["start_time"]
    end_time = request.form["end_time"]
    session_count = int(request.form["session_count"])

    generated_plan = generate_auto_timetable(notes, timetable, start_time, end_time, session_count)

    analysis = analyze_learning(notes)
    suggestions = generate_suggestions(analysis)
    ai_timetable_suggestions = generate_ai_timetable_suggestions(notes, timetable)

    return render_template(
        "index.html",
        notes=notes,
        timetable=timetable,
        analysis=analysis,
        suggestions=suggestions,
        ai_timetable_suggestions=ai_timetable_suggestions,
        generated_plan=generated_plan
    )
    @app.route("/save-generated-plan", methods=["POST"])
    def save_generated_plan():
        db = get_db()

    subject_list = request.form.getlist("subject")
    task_list = request.form.getlist("task")
    time_list = request.form.getlist("reminder_time")

    for subject, task, reminder_time in zip(subject_list, task_list, time_list):
        db.execute("""
            INSERT INTO timetable (subject, task, reminder_time, repeat_daily, status, created_at)
            VALUES (?, ?, ?, 0, 'pending', ?)
        """, (subject, task, reminder_time, datetime.now().strftime("%Y-%m-%d %H:%M")))

    db.commit()
    return redirect("/")

@app.route("/add", methods=["POST"])
def add_note():
    raw = request.form["raw_text"]
    corrected = correct_note(raw)

    db = get_db()
    db.execute(
        "INSERT INTO notes (raw_text, corrected_text, created_at) VALUES (?, ?, ?)",
        (raw, corrected, datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    db.commit()

    return redirect("/")


@app.route("/add-timetable", methods=["POST"])
def add_timetable():
    subject = request.form["subject"]
    task = request.form["task"]
    time = request.form["reminder_time"]
    repeat = 1 if request.form.get("repeat_daily") else 0

    db = get_db()
    db.execute("""
        INSERT INTO timetable (subject, task, reminder_time, repeat_daily, status, created_at)
        VALUES (?, ?, ?, ?, 'pending', ?)
    """, (subject, task, time, repeat, datetime.now().strftime("%Y-%m-%d %H:%M")))
    db.commit()

    return redirect("/")


@app.route("/get-timetable")
def get_timetable():
    db = get_db()
    rows = db.execute("SELECT * FROM timetable").fetchall()

    data = []
    for r in rows:
        data.append({
            "id": r["id"],
            "subject": r["subject"],
            "task": r["task"],
            "reminder_time": r["reminder_time"],
            "status": r["status"],
            "message": get_smart_reminder_message(r["subject"], r["task"])
        })

    return jsonify(data)


@app.route("/mark-task-done/<int:id>", methods=["POST"])
def mark_done(id):
    db = get_db()
    db.execute("UPDATE timetable SET status='done' WHERE id=?", (id,))
    db.commit()
    return jsonify({"success": True})


@app.route("/reset-daily-tasks", methods=["POST"])
def reset_tasks():
    db = get_db()
    db.execute("UPDATE timetable SET status='pending' WHERE repeat_daily=1")
    db.commit()
    return jsonify({"success": True})


@app.route("/correct", methods=["POST"])
def correct_api():
    text = request.json.get("text", "")
    return jsonify({"success": True, "corrected_text": correct_note(text)})


@app.route("/explain", methods=["POST"])
def explain():
    word = request.json.get("word", "").lower()

    return jsonify({
        "success": True,
        "data": {
            "title": word,
            "meaning": f"{word} meaning",
            "explanation": f"{word} explanation",
            "example": f"{word} example",
            "use_case": f"{word} use case"
        }
    })
    

@app.route("/chat", methods=["POST"])
def chat():
    msg = request.json.get("message", "")
    return jsonify({"reply": ai_friend_response(msg)})


@app.route("/speech-to-text", methods=["POST"])
def speech():
    file = request.files["audio"]
    path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(path)

    try:
        import whisper
        model = whisper.load_model("base")
        result = model.transcribe(path)
        return jsonify({"success": True, "text": result["text"]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ------------------ RUN ------------------

if __name__ == "__main__":
    init_db()
    app.run(debug=True)