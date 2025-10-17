from flask import Flask, request, jsonify
import sqlite3
from werkzeug.exceptions import HTTPException

# ============================================
# OpenTelemetry Imports - METRICS + TRACING
# ============================================

# Metrics
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.prometheus import PrometheusMetricReader
import prometheus_client

# Tracing
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Instrumentation
from opentelemetry.instrumentation.flask import FlaskInstrumentor

# ============================================
# Database Setup
# ============================================
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

# ============================================
# Flask App
# ============================================
app = Flask(__name__)

# ============================================
# OpenTelemetry Setup
# ============================================

# Create resource (service identification)
resource = Resource.create({
    "service.name": "flask-todo",
    "service.version": "1.0.0",
    "deployment.environment": "development"
})

# --- METRICS SETUP ---
prometheus_reader = PrometheusMetricReader()
meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[prometheus_reader]
)
metrics.set_meter_provider(meter_provider)
meter = metrics.get_meter("flask-todo-meter")

# Custom error counter
error_counter = meter.create_counter(
    "http_5xx_requests_total",
    description="Total number of 5xx responses",
)

# --- TRACING SETUP ---
tracer_provider = TracerProvider(resource=resource)
trace.set_tracer_provider(tracer_provider)

# Configure OTLP exporter to send traces to Jaeger
otlp_exporter = OTLPSpanExporter(
    endpoint="http://jaeger:4317",
    insecure=True
)

tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
tracer = trace.get_tracer(__name__)

# --- INSTRUMENTATION ---
# Auto-instrument Flask (adds spans + metrics automatically)
FlaskInstrumentor().instrument_app(app)

print("✅ OpenTelemetry initialized:")
print("   📊 Metrics: Prometheus on /metrics")
print("   🔍 Traces: OTLP to jaeger:4317")

# ============================================
# Error Handler
# ============================================
@app.errorhandler(Exception)
def handle_exception(e):
    # Add span context for errors
    current_span = trace.get_current_span()
    if current_span:
        current_span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
        current_span.record_exception(e)
    
    # Count 5xx errors
    if isinstance(e, HTTPException) and 500 <= e.code < 600:
        error_counter.add(1, {"endpoint": request.path})
    
    return jsonify(error=str(e)), getattr(e, "code", 500)

# ============================================
# Routes
# ============================================

@app.route("/tasks", methods=["GET"])
def get_tasks():
    # Add custom attributes to the auto-instrumented span
    current_span = trace.get_current_span()
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    rows = c.execute("SELECT id, task, done FROM todos").fetchall()
    conn.close()
    
    tasks = [{"id": r[0], "task": r[1], "done": bool(r[2])} for r in rows]
    
    # Add span attribute
    if current_span:
        current_span.set_attribute("tasks.count", len(tasks))
    
    return jsonify(tasks)

@app.route("/tasks", methods=["POST"])
def add_task():
    data = request.json
    
    if not data or "task" not in data:
        return jsonify({"error": "Task required"}), 400
    
    # Create a child span for DB operation
    with tracer.start_as_current_span("db_insert_task") as span:
        span.set_attribute("db.system", "sqlite")
        span.set_attribute("db.statement", "INSERT INTO todos")
        span.set_attribute("task.text", data["task"])
        
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO todos (task, done) VALUES (?, ?)", (data["task"], 0))
        conn.commit()
        conn.close()
    
    return jsonify({"message": "Task added"}), 201

@app.route("/tasks/<int:task_id>", methods=["PUT"])
def update_task(task_id):
    data = request.json
    
    current_span = trace.get_current_span()
    if current_span:
        current_span.set_attribute("task.id", task_id)
    
    with tracer.start_as_current_span("db_update_task") as span:
        span.set_attribute("db.system", "sqlite")
        span.set_attribute("task.id", task_id)
        
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        if "task" in data:
            c.execute("UPDATE todos SET task=? WHERE id=?", (data["task"], task_id))
            span.set_attribute("update.field", "task")
        
        if "done" in data:
            c.execute("UPDATE todos SET done=? WHERE id=?", (int(data["done"]), task_id))
            span.set_attribute("update.field", "done")
            span.set_attribute("task.done", data["done"])
        
        conn.commit()
        conn.close()
    
    return jsonify({"message": "Task updated"})

@app.route("/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    current_span = trace.get_current_span()
    if current_span:
        current_span.set_attribute("task.id", task_id)
    
    with tracer.start_as_current_span("db_delete_task") as span:
        span.set_attribute("db.system", "sqlite")
        span.set_attribute("task.id", task_id)
        
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("DELETE FROM todos WHERE id=?", (task_id,))
        conn.commit()
        conn.close()
    
    return jsonify({"message": "Task deleted"})

# ============================================
# Observability Endpoints
# ============================================

@app.route("/metrics")
def metrics_endpoint():
    """Prometheus metrics endpoint"""
    return prometheus_client.generate_latest(), 200, {
        "Content-Type": prometheus_client.CONTENT_TYPE_LATEST
    }

@app.route("/health")
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "flask-todo",
        "metrics_enabled": True,
        "tracing_enabled": True
    }), 200

# ============================================
# Main
# ============================================
if __name__ == "__main__":
    init_db()
    print("🚀 Starting Flask Todo App")
    print("   📊 Metrics: http://localhost:8000/metrics")
    print("   🏥 Health: http://localhost:8000/health")
    print("   🔍 Traces: Sent to Jaeger (http://localhost:16686)")
    app.run(host="0.0.0.0", port=8000, debug=True)