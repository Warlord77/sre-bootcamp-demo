from flask import Flask, jsonify, request
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
import logging
import json
import os
import requests
from datetime import datetime

app = Flask(__name__)

# -----------------------------
# In-memory task storage
# -----------------------------
tasks = []
next_id = 1

# -----------------------------
# Prometheus Metrics
# -----------------------------
REQUEST_COUNT = Counter("http_requests_total", "Total HTTP Requests", ["method", "endpoint", "status"])
TASKS_TOTAL = Gauge("tasks_total", "Total number of tasks")

# -----------------------------
# VictoriaLogs Configuration
# -----------------------------
VICTORIA_ACCOUNT_ID = os.getenv("VICTORIA_ACCOUNT_ID", "0")
VICTORIA_PROJECT_ID = os.getenv("VICTORIA_PROJECT_ID", "0")

# Path-based partition URL
VICTORIA_LOGS_URL = (
    f"http://victorialogs:9428/insert/{VICTORIA_ACCOUNT_ID}/{VICTORIA_PROJECT_ID}/jsonline"
    "?_time_field=@timestamp&_msg_field=message&_stream_fields=service"
)

# -----------------------------
# Custom Logging to VictoriaLogs
# -----------------------------
class VictoriaLogsHandler(logging.Handler):
    def emit(self, record):
        try:
            log_entry = self.format(record) + "\n"
            headers = {"Content-Type": "application/stream+json"}
            # Send non-blocking, lightweight log insert
            requests.post(VICTORIA_LOGS_URL, data=log_entry.encode("utf-8"), headers=headers, timeout=1)
        except Exception:
            pass  # Avoid crashing on log errors

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log = {
            "@timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "service": "flask-todo",
        }
        if hasattr(record, "args") and isinstance(record.args, dict):
            log.update(record.args)
        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)
        return json.dumps(log)

# Setup logger
logger = logging.getLogger("flask-todo")
logger.setLevel(logging.INFO)
vl_handler = VictoriaLogsHandler()
vl_handler.setFormatter(JSONFormatter())
logger.addHandler(vl_handler)

# -----------------------------
# Flask Routes
# -----------------------------
@app.route("/metrics")
def metrics_endpoint():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}

@app.route("/tasks", methods=["GET"])
def get_tasks():
    REQUEST_COUNT.labels("GET", "/tasks", 200).inc()
    logger.info("Fetched all tasks", extra={"count": len(tasks)})
    return jsonify(tasks)

@app.route("/tasks", methods=["POST"])
def create_task():
    global next_id
    data = request.get_json(force=True)
    task = {"id": next_id, "task": data["task"], "done": False}
    tasks.append(task)
    next_id += 1
    TASKS_TOTAL.set(len(tasks))
    REQUEST_COUNT.labels("POST", "/tasks", 201).inc()
    logger.info("Created task", extra={"task_id": task["id"], "task": task["task"]})
    return jsonify(task), 201

@app.route("/tasks/<int:task_id>", methods=["PUT"])
def update_task(task_id):
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        REQUEST_COUNT.labels("PUT", "/tasks/<id>", 404).inc()
        logger.warning("Task not found", extra={"task_id": task_id})
        return jsonify({"error": "Task not found"}), 404
    task["done"] = request.get_json(force=True).get("done", task["done"])
    REQUEST_COUNT.labels("PUT", "/tasks/<id>", 200).inc()
    logger.info("Updated task", extra={"task_id": task_id, "done": task["done"]})
    return jsonify(task)

@app.route("/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    global tasks
    tasks = [t for t in tasks if t["id"] != task_id]
    TASKS_TOTAL.set(len(tasks))
    REQUEST_COUNT.labels("DELETE", "/tasks/<id>", 200).inc()
    logger.info("Deleted task", extra={"task_id": task_id})
    return jsonify({"result": "Deleted"})

@app.errorhandler(404)
def not_found(e):
    REQUEST_COUNT.labels(request.method, "unknown", 404).inc()
    logger.warning("404 Not Found", extra={"path": request.path})
    return jsonify({"error": "Not Found"}), 404

# -----------------------------
# Run App
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
