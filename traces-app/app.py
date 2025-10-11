# app.py
import logging
import json
import sqlite3
import time
from flask import Flask, request, jsonify
from werkzeug.exceptions import HTTPException

# -------------------------
# Structured JSON Logging
# -------------------------
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "time": self.formatTime(record, self.datefmt),
        }
        # include extra if present
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            log_record.update(record.extra)
        return json.dumps(log_record)

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger = logging.getLogger("flask-todo")
logger.setLevel(logging.INFO)
# avoid duplicate handlers
if not logger.handlers:
    logger.addHandler(handler)
else:
    # replace existing handlers with json one
    logger.handlers = [handler]

# reduce werkzeug access log noise (optional)
logging.getLogger("werkzeug").setLevel(logging.ERROR)

# -------------------------
# Flask app
# -------------------------
app = Flask(__name__)
DB_NAME = "todos.db"

# -------------------------
# OpenTelemetry: Metrics + Tracing
# -------------------------
from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

# Tracing exporters
from opentelemetry.exporter.jaeger.thrift import JaegerExporter

# Metrics exporter (Prometheus)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.exporter.prometheus import PrometheusMetricReader
import prometheus_client

# Setup resource (service metadata)
resource = Resource.create({"service.name": "flask-todo"})

# -------- Tracing ----------
tracer_provider = TracerProvider(resource=resource)
trace.set_tracer_provider(tracer_provider)

# Configure Jaeger exporter (sends to Jaeger agent at jaeger:6831)
jaeger_exporter = JaegerExporter(
    agent_host_name="jaeger",
    agent_port=6831,
)

tracer_provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
tracer = trace.get_tracer(__name__)

# Auto-instrument Flask + Requests
FlaskInstrumentor().instrument_app(app)
RequestsInstrumentor().instrument()

# -------- Metrics ----------
reader = PrometheusMetricReader()
meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
metrics.set_meter_provider(meter_provider)
meter = metrics.get_meter("flask-todo-meter")

# Counters
request_counter = meter.create_counter(
    "http_requests_total",
    description="Total HTTP requests",
)
error_counter = meter.create_counter(
    "http_5xx_requests_total",
    description="Total number of 5xx responses",
)

# Histogram (manual example for DB op)
db_latency_hist = meter.create_histogram(
    "db_operation_duration_seconds",
    description="DB operation duration in seconds",
)

# -------------------------
# DB helpers
# -------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task TEXT NOT NULL,
            done INTEGER DEFAULT 0
        )"""
    )
    conn.commit()
    conn.close()
    logger.info("Database initialized")

def db_execute(query, params=(), span_name="db_query"):
    """Helper to run small DB query inside a manual span and record latency metric."""
    start = time.time()
    with tracer.start_as_current_span(span_name) as span:
        try:
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute(query, params)
            rows = c.fetchall()
            conn.commit()
            conn.close()
            duration = time.time() - start
            db_latency_hist.record(duration, {"query": query.split()[0]})
            span.set_attribute("db.rows_returned", len(rows))
            return rows
        except Exception as ex:
            span.record_exception(ex)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(ex)))
            raise

# -------------------------
# Error handling
# -------------------------
@app.errorhandler(Exception)
def handle_exception(e):
    # Increment counters and log
    if isinstance(e, HTTPException):
        code = e.code
        if 500 <= code < 600:
            error_counter.add(1, {"endpoint": request.path})
            logger.error(f"HTTP {code} at {request.path}")
        else:
            logger.warning(f"HTTP {code} at {request.path}")
        return jsonify(error=str(e)), code

    # non-HTTP exceptions -> produce 500
    error_counter.add(1, {"endpoint": request.path})
    logger.exception("Unexpected error")
    return jsonify(error=str(e)), 500

# -------------------------
# Routes
# -------------------------
@app.route("/tasks", methods=["GET"])
def get_tasks():
    request_counter.add(1, {"method": "GET", "endpoint": "/tasks"})
    logger.info("Fetching tasks")
    # manual span for DB read
    rows = db_execute("SELECT id, task, done FROM todos")
    tasks = [{"id": r[0], "task": r[1], "done": bool(r[2])} for r in rows]
    return jsonify(tasks)

@app.route("/tasks", methods=["POST"])
def add_task():
    request_counter.add(1, {"method": "POST", "endpoint": "/tasks"})
    data = request.json
    if not data or "task" not in data:
        logger.warning("Bad request: task missing")
        return jsonify({"error": "Task required"}), 400

    with tracer.start_as_current_span("insert_task") as span:
        span.set_attribute("task.length", len(data["task"]))
        # insert via helper
        db_execute("INSERT INTO todos (task, done) VALUES (?, ?)", (data["task"], 0), span_name="db_insert")
    logger.info(f"Task added: {data['task']}")
    return jsonify({"message": "Task added"}), 201

@app.route("/tasks/<int:task_id>", methods=["PUT"])
def update_task(task_id):
    request_counter.add(1, {"method": "PUT", "endpoint": "/tasks/<id>"})
    data = request.json or {}
    logger.info(f"Updating task {task_id}")
    with tracer.start_as_current_span("update_task") as span:
        if "task" in data:
            db_execute("UPDATE todos SET task=? WHERE id=?", (data["task"], task_id), span_name="db_update")
        if "done" in data:
            db_execute("UPDATE todos SET done=? WHERE id=?", (int(data["done"]), task_id), span_name="db_update")
    return jsonify({"message": "Task updated"})

@app.route("/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    request_counter.add(1, {"method": "DELETE", "endpoint": "/tasks/<id>"})
    logger.info(f"Deleting task {task_id}")
    with tracer.start_as_current_span("delete_task"):
        db_execute("DELETE FROM todos WHERE id=?", (task_id,), span_name="db_delete")
    return jsonify({"message": "Task deleted"})

# Expose Prometheus metrics endpoint (Prometheus scrapes this)
@app.route("/metrics")
def metrics_endpoint():
    # Prometheus client generate_latest() returns bytes; Flask will handle it
    return prometheus_client.generate_latest(), 200, {"Content-Type": prometheus_client.CONTENT_TYPE_LATEST}

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
