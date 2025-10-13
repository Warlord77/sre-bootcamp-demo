from flask import Flask, request, jsonify
import sqlite3
from werkzeug.exceptions import HTTPException

# --- OTEL Imports ---
import opentelemetry
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.flask import FlaskInstrumentor
import prometheus_client

# --- DB Setup ---
DB_NAME = "todos.db"

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

# --- Flask App ---
app = Flask(__name__)

# --- OTel Metrics ---
reader = PrometheusMetricReader()
provider = MeterProvider(resource=Resource.create({"service.name": "flask-todo"}), metric_readers=[reader])
metrics.set_meter_provider(provider)
meter = metrics.get_meter("flask-todo-meter")

# Custom metric for 5xx errors
error_counter = meter.create_counter(
    "http_5xx_requests_total",
    description="Total number of 5xx responses",
)

# Auto-instrument Flask
FlaskInstrumentor().instrument_app(app)

@app.errorhandler(Exception)
def handle_exception(e):
    # If it's an HTTPException with a 5xx, count it
    if isinstance(e, HTTPException) and 500 <= e.code < 600:
        error_counter.add(1, {"endpoint": request.path})
    return jsonify(error=str(e)), getattr(e, "code", 500)

# --- Routes ---
@app.route("/tasks", methods=["GET"])
def get_tasks():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    rows = c.execute("SELECT id, task, done FROM todos").fetchall()
    conn.close()
    return jsonify([{"id": r[0], "task": r[1], "done": bool(r[2])} for r in rows])

@app.route("/tasks", methods=["POST"])
def add_task():
    data = request.json
    if not data or "task" not in data:
        return jsonify({"error": "Task required"}), 400
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO todos (task, done) VALUES (?, ?)", (data["task"], 0))
    conn.commit()
    conn.close()
    return jsonify({"message": "Task added"}), 201

@app.route("/tasks/<int:task_id>", methods=["PUT"])
def update_task(task_id):
    data = request.json
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    if "task" in data:
        c.execute("UPDATE todos SET task=? WHERE id=?", (data["task"], task_id))
    if "done" in data:
        c.execute("UPDATE todos SET done=? WHERE id=?", (int(data["done"]), task_id))
    conn.commit()
    conn.close()
    return jsonify({"message": "Task updated"})

@app.route("/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM todos WHERE id=?", (task_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Task deleted"})

# Expose /metrics endpoint
@app.route("/metrics")
def metrics_endpoint():
    return prometheus_client.generate_latest(), 200, {"Content-Type": prometheus_client.CONTENT_TYPE_LATEST}

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8000, debug=True)
