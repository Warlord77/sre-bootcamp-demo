from flask import Flask, request, jsonify
import sqlite3

app = Flask(__name__)
DB_NAME = "todos.db"

# -----------------------
# DB Helpers
# -----------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS todos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task TEXT NOT NULL,
                    done INTEGER DEFAULT 0
                )''')
    conn.commit()
    conn.close()

def query_db(query, args=(), one=False):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(query, args)
    rv = c.fetchall()
    conn.commit()
    conn.close()
    return (rv[0] if rv else None) if one else rv

# -----------------------
# API Routes
# -----------------------

# 1. Get all tasks
@app.route("/tasks", methods=["GET"])
def get_tasks():
    rows = query_db("SELECT id, task, done FROM todos")
    tasks = [{"id": r[0], "task": r[1], "done": bool(r[2])} for r in rows]
    return jsonify(tasks)

# 2. Add new task
@app.route("/tasks", methods=["POST"])
def add_task():
    data = request.json
    task = data.get("task")
    if not task:
        return jsonify({"error": "Task is required"}), 400
    query_db("INSERT INTO todos (task, done) VALUES (?, ?)", (task, 0))
    return jsonify({"message": "Task added successfully"}), 201

# 3. Update task
@app.route("/tasks/<int:task_id>", methods=["PUT"])
def update_task(task_id):
    data = request.json
    task = data.get("task")
    done = data.get("done")

    if task is not None:
        query_db("UPDATE todos SET task=? WHERE id=?", (task, task_id))

    if done is not None:
        query_db("UPDATE todos SET done=? WHERE id=?", (int(done), task_id))

    return jsonify({"message": "Task updated successfully"})

# 4. Delete task
@app.route("/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    query_db("DELETE FROM todos WHERE id=?", (task_id,))
    return jsonify({"message": "Task deleted successfully"})

# -----------------------
# Start App
# -----------------------
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
