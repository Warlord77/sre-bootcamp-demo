# ============================================
# app.py - Complete Observability (Traces + Metrics + Logs)
# ============================================

from flask import Flask, request, jsonify
import logging
import time
import json

# ============================================
# OpenTelemetry Imports
# ============================================

# Tracing
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

# Metrics
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.exporter.prometheus import PrometheusMetricReader

# Instrumentation
from opentelemetry.instrumentation.flask import FlaskInstrumentor

# Prometheus
import prometheus_client

# ============================================
# Structured JSON Logging
# ============================================

class JsonFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""
    def format(self, record):
        # Get current span context for correlation
        span = trace.get_current_span()
        span_context = span.get_span_context()
        
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add trace context for correlation
        if span_context.is_valid:
            log_record["trace_id"] = format(span_context.trace_id, '032x')
            log_record["span_id"] = format(span_context.span_id, '016x')
        
        # Add extra fields if present
        if hasattr(record, 'extra_fields'):
            log_record.update(record.extra_fields)
        
        return json.dumps(log_record)

# Configure logging
handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger = logging.getLogger("flask-todo")
logger.setLevel(logging.INFO)
logger.handlers = [handler]

# Reduce werkzeug noise
logging.getLogger("werkzeug").setLevel(logging.WARNING)

# ============================================
# Flask App
# ============================================

app = Flask(__name__)

# In-memory task storage
tasks = {}

# ============================================
# OpenTelemetry Setup
# ============================================

# Create resource
resource = Resource.create({
    "service.name": "flask-todo",
    "service.version": "2.0.0",
    "deployment.environment": "production"
})

# --- TRACING SETUP ---
tracer_provider = TracerProvider(resource=resource)
trace.set_tracer_provider(tracer_provider)

# Configure OTLP exporter
otlp_exporter = OTLPSpanExporter(
    endpoint="http://jaeger:4317",
    insecure=True
)
tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
tracer = trace.get_tracer(__name__)

# --- METRICS SETUP ---
prometheus_reader = PrometheusMetricReader()
meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[prometheus_reader]
)
metrics.set_meter_provider(meter_provider)
meter = metrics.get_meter("flask-todo-meter")

# Custom metrics
task_counter = meter.create_counter(
    "tasks_total",
    description="Total number of tasks created",
)

task_operations = meter.create_counter(
    "task_operations_total",
    description="Total task operations",
)

error_counter = meter.create_counter(
    "http_errors_total",
    description="Total HTTP errors",
)

# --- AUTO-INSTRUMENTATION ---
FlaskInstrumentor().instrument_app(app)

logger.info("🚀 OpenTelemetry initialized", extra={
    'extra_fields': {
        'tracing_enabled': True,
        'metrics_enabled': True,
        'jaeger_endpoint': 'jaeger:4317'
    }
})

# ============================================
# Helper Functions
# ============================================

def log_with_context(level, message, **kwargs):
    """Log with trace context and extra fields"""
    extra = {'extra_fields': kwargs}
    getattr(logger, level)(message, extra=extra)

# ============================================
# Routes
# ============================================

@app.route("/", methods=["GET"])
def index():
    log_with_context('info', 'Root endpoint accessed', endpoint='/')
    return jsonify({
        "message": "Flask ToDo App - Complete Observability Stack",
        "endpoints": {
            "tasks": "/tasks",
            "metrics": "/metrics",
            "health": "/health"
        },
        "observability": {
            "traces": "Jaeger on port 16686",
            "metrics": "Prometheus on port 9090",
            "logs": "Loki via Grafana on port 3000"
        }
    })

@app.route("/health", methods=["GET"])
def health():
    current_span = trace.get_current_span()
    if current_span:
        current_span.set_attribute("health.check", "ok")
        current_span.set_attribute("tasks.count", len(tasks))
    
    log_with_context('info', 'Health check', 
                     status='healthy',
                     task_count=len(tasks))
    
    return jsonify({
        "status": "healthy",
        "service": "flask-todo",
        "tasks_count": len(tasks),
        "observability": {
            "tracing": "enabled",
            "metrics": "enabled",
            "logging": "enabled"
        }
    }), 200

@app.route("/tasks", methods=["GET"])
def get_tasks():
    current_span = trace.get_current_span()
    
    with tracer.start_as_current_span("fetch_all_tasks") as span:
        span.set_attribute("task.count", len(tasks))
        
        task_list = list(tasks.values())
        
        log_with_context('info', 'Fetching all tasks',
                        task_count=len(task_list),
                        operation='get_all')
        
        span.set_status(trace.Status(trace.StatusCode.OK))
    
    if current_span:
        current_span.set_attribute("response.task_count", len(task_list))
    
    return jsonify(task_list), 200

@app.route("/tasks", methods=["POST"])
def create_task():
    current_span = trace.get_current_span()
    
    data = request.get_json()
    
    if not data or "task" not in data:
        log_with_context('warning', 'Bad request - missing task field',
                        error='missing_field',
                        endpoint='/tasks')
        
        if current_span:
            current_span.set_attribute("error", "missing_task_field")
            current_span.set_status(trace.Status(trace.StatusCode.ERROR))
        
        error_counter.add(1, {"endpoint": "/tasks", "status": "400"})
        return jsonify({"error": "Missing 'task' field"}), 400
    
    with tracer.start_as_current_span("create_task_operation") as span:
        task_id = len(tasks) + 1
        task_text = data["task"]
        
        span.set_attribute("task.id", task_id)
        span.set_attribute("task.text", task_text)
        span.set_attribute("operation", "create")
        
        tasks[task_id] = {
            "id": task_id,
            "task": task_text,
            "done": False
        }
        
        # Update metrics
        task_counter.add(1)
        task_operations.add(1, {"operation": "create"})
        
        log_with_context('info', 'Task created',
                        task_id=task_id,
                        task_text=task_text,
                        operation='create')
        
        span.set_status(trace.Status(trace.StatusCode.OK))
    
    if current_span:
        current_span.set_attribute("task.created_id", task_id)
    
    return jsonify(tasks[task_id]), 201

@app.route("/tasks/<int:task_id>", methods=["GET"])
def get_task(task_id):
    current_span = trace.get_current_span()
    if current_span:
        current_span.set_attribute("task.id", task_id)
    
    if task_id not in tasks:
        log_with_context('warning', 'Task not found',
                        task_id=task_id,
                        error='not_found')
        
        if current_span:
            current_span.set_status(trace.Status(trace.StatusCode.ERROR))
        
        error_counter.add(1, {"endpoint": "/tasks/id", "status": "404"})
        return jsonify({"error": "Task not found"}), 404
    
    log_with_context('info', 'Task retrieved',
                    task_id=task_id,
                    operation='get')
    
    return jsonify(tasks[task_id]), 200

@app.route("/tasks/<int:task_id>", methods=["PUT"])
def update_task(task_id):
    current_span = trace.get_current_span()
    if current_span:
        current_span.set_attribute("task.id", task_id)
        current_span.set_attribute("operation", "update")
    
    if task_id not in tasks:
        log_with_context('warning', 'Task not found for update',
                        task_id=task_id,
                        error='not_found')
        
        if current_span:
            current_span.set_status(trace.Status(trace.StatusCode.ERROR))
        
        error_counter.add(1, {"endpoint": "/tasks/id", "status": "404"})
        return jsonify({"error": "Task not found"}), 404
    
    data = request.get_json()
    
    if not data or "done" not in data:
        log_with_context('warning', 'Bad request - missing done field',
                        task_id=task_id,
                        error='missing_field')
        
        if current_span:
            current_span.set_status(trace.Status(trace.StatusCode.ERROR))
        
        error_counter.add(1, {"endpoint": "/tasks/id", "status": "400"})
        return jsonify({"error": "Missing 'done' field"}), 400
    
    with tracer.start_as_current_span("update_task_operation") as span:
        old_status = tasks[task_id]["done"]
        new_status = data["done"]
        
        span.set_attribute("task.id", task_id)
        span.set_attribute("task.old_status", old_status)
        span.set_attribute("task.new_status", new_status)
        
        tasks[task_id]["done"] = new_status
        
        task_operations.add(1, {"operation": "update"})
        
        log_with_context('info', 'Task updated',
                        task_id=task_id,
                        old_status=old_status,
                        new_status=new_status,
                        operation='update')
        
        span.set_status(trace.Status(trace.StatusCode.OK))
    
    return jsonify(tasks[task_id]), 200

@app.route("/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    current_span = trace.get_current_span()
    if current_span:
        current_span.set_attribute("task.id", task_id)
        current_span.set_attribute("operation", "delete")
    
    if task_id not in tasks:
        log_with_context('warning', 'Task not found for deletion',
                        task_id=task_id,
                        error='not_found')
        
        if current_span:
            current_span.set_status(trace.Status(trace.StatusCode.ERROR))
        
        error_counter.add(1, {"endpoint": "/tasks/id", "status": "404"})
        return jsonify({"error": "Task not found"}), 404
    
    with tracer.start_as_current_span("delete_task_operation") as span:
        deleted_task = tasks[task_id]["task"]
        
        span.set_attribute("task.id", task_id)
        span.set_attribute("task.text", deleted_task)
        
        del tasks[task_id]
        
        task_operations.add(1, {"operation": "delete"})
        
        log_with_context('info', 'Task deleted',
                        task_id=task_id,
                        task_text=deleted_task,
                        operation='delete')
        
        span.set_status(trace.Status(trace.StatusCode.OK))
    
    return jsonify({"message": "Task deleted"}), 200

# ============================================
# Metrics Endpoint
# ============================================

@app.route("/metrics")
def metrics_endpoint():
    log_with_context('debug', 'Metrics endpoint accessed')
    return prometheus_client.generate_latest(), 200, {
        "Content-Type": prometheus_client.CONTENT_TYPE_LATEST
    }

# ============================================
# Error Handlers
# ============================================

@app.errorhandler(404)
def not_found(error):
    current_span = trace.get_current_span()
    if current_span:
        current_span.set_attribute("error.type", "404")
        current_span.set_attribute("error.path", request.path)
        current_span.set_status(trace.Status(trace.StatusCode.ERROR))
    
    log_with_context('warning', '404 Not Found',
                    path=request.path,
                    method=request.method,
                    error='not_found')
    
    error_counter.add(1, {"endpoint": request.path, "status": "404"})
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    current_span = trace.get_current_span()
    if current_span:
        current_span.set_attribute("error.type", "500")
        current_span.record_exception(error)
        current_span.set_status(trace.Status(trace.StatusCode.ERROR, str(error)))
    
    log_with_context('error', '500 Internal Server Error',
                    error=str(error),
                    path=request.path,
                    method=request.method)
    
    error_counter.add(1, {"endpoint": request.path, "status": "500"})
    return jsonify({"error": "Internal server error"}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    current_span = trace.get_current_span()
    if current_span:
        current_span.record_exception(e)
        current_span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
    
    log_with_context('error', 'Unhandled exception',
                    error=str(e),
                    exception_type=type(e).__name__)
    
    error_counter.add(1, {"endpoint": request.path, "status": "500"})
    return jsonify({"error": str(e)}), 500

# ============================================
# Main
# ============================================

if __name__ == "__main__":
    logger.info("🚀 Starting Flask ToDo App with Complete Observability", extra={
        'extra_fields': {
            'port': 5000,
            'host': '0.0.0.0',
            'environment': 'production'
        }
    })
    
    logger.info("📊 Metrics: http://localhost:9090 (Prometheus)", extra={
        'extra_fields': {'metrics_endpoint': '/metrics'}
    })
    
    logger.info("🔍 Traces: http://localhost:16686 (Jaeger)", extra={
        'extra_fields': {'jaeger_endpoint': 'jaeger:4317'}
    })
    
    logger.info("📋 Logs: http://localhost:3000 (Grafana/Loki)", extra={
        'extra_fields': {'loki_endpoint': 'loki:3100'}
    })
    
    app.run(host="0.0.0.0", port=5000)