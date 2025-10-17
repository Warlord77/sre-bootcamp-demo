# ============================================
# app.py - Complete Observability with SigNoz (Traces + Metrics + Logs)
# ============================================

from flask import Flask, request, jsonify
import logging
import time
import sys

print("🚀 Starting Flask Todo App...", flush=True)

# ============================================
# Flask App (Initialize Early)
# ============================================

app = Flask(__name__)
tasks = {}

# ============================================
# OpenTelemetry Setup with Error Handling
# ============================================

try:
    print("📦 Importing OpenTelemetry packages...", flush=True)
    
    # Tracing
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource

    # Metrics
    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider, PeriodicExportingMetricReader
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

    # Logging
    from opentelemetry import _logs
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

    # Instrumentation
    from opentelemetry.instrumentation.flask import FlaskInstrumentor

    print("✅ OpenTelemetry packages imported successfully", flush=True)

    # Create resource
    resource = Resource.create({
        "service.name": "flask-todo",
        "service.version": "3.0.0",
        "deployment.environment": "production"
    })

    # SigNoz OTLP endpoint
    SIGNOZ_ENDPOINT = "http://signoz-otel-collector:4317"
    print(f"🔌 Connecting to SigNoz at {SIGNOZ_ENDPOINT}", flush=True)

    # --- TRACING SETUP ---
    tracer_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)

    otlp_trace_exporter = OTLPSpanExporter(
        endpoint=SIGNOZ_ENDPOINT,
        insecure=True
    )
    tracer_provider.add_span_processor(BatchSpanProcessor(otlp_trace_exporter))
    tracer = trace.get_tracer(__name__)
    print("✅ Tracing configured", flush=True)

    # --- METRICS SETUP ---
    otlp_metric_exporter = OTLPMetricExporter(
        endpoint=SIGNOZ_ENDPOINT,
        insecure=True
    )

    metric_reader = PeriodicExportingMetricReader(
        otlp_metric_exporter,
        export_interval_millis=5000
    )

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[metric_reader]
    )
    metrics.set_meter_provider(meter_provider)
    meter = metrics.get_meter("flask-todo-meter")

    # Custom metrics
    task_counter = meter.create_counter("tasks_total", description="Total number of tasks created")
    task_operations = meter.create_counter("task_operations_total", description="Total task operations")
    error_counter = meter.create_counter("http_errors_total", description="Total HTTP errors")
    request_duration = meter.create_histogram("http_request_duration_seconds", description="HTTP request duration in seconds")
    print("✅ Metrics configured", flush=True)

    # --- LOGGING SETUP ---
    logger_provider = LoggerProvider(resource=resource)
    _logs.set_logger_provider(logger_provider)

    otlp_log_exporter = OTLPLogExporter(
        endpoint=SIGNOZ_ENDPOINT,
        insecure=True
    )

    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(otlp_log_exporter)
    )

    handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("flask-todo")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    print("✅ Logging configured", flush=True)

    # --- AUTO-INSTRUMENTATION ---
    FlaskInstrumentor().instrument_app(app)
    print("✅ Flask auto-instrumentation enabled", flush=True)

    OTEL_ENABLED = True
    print("🎉 OpenTelemetry fully initialized!", flush=True)

except Exception as e:
    print(f"⚠️  OpenTelemetry initialization failed: {e}", flush=True)
    print("⚠️  App will run WITHOUT observability", flush=True)
    OTEL_ENABLED = False
    
    # Create dummy logger
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("flask-todo")
    
    # Create dummy objects to prevent errors
    class DummyTracer:
        def start_as_current_span(self, name):
            class DummySpan:
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def set_attribute(self, *args): pass
                def set_status(self, *args): pass
            return DummySpan()
    
    tracer = DummyTracer()
    
    class DummyCounter:
        def add(self, *args, **kwargs): pass
    
    class DummyHistogram:
        def record(self, *args, **kwargs): pass
    
    task_counter = DummyCounter()
    task_operations = DummyCounter()
    error_counter = DummyCounter()
    request_duration = DummyHistogram()

# ============================================
# Helper Functions
# ============================================

def log_with_trace_context(level, message, **kwargs):
    """Log with automatic trace context correlation"""
    if not OTEL_ENABLED:
        getattr(logger, level)(f"{message} {kwargs}")
        return
    
    try:
        span = trace.get_current_span()
        span_context = span.get_span_context()
        
        extra_data = kwargs.copy()
        
        if span_context.is_valid:
            extra_data['trace_id'] = format(span_context.trace_id, '032x')
            extra_data['span_id'] = format(span_context.span_id, '016x')
        
        getattr(logger, level)(message, extra=extra_data)
    except:
        getattr(logger, level)(f"{message} {kwargs}")

# ============================================
# Routes
# ============================================

@app.route("/", methods=["GET"])
def index():
    log_with_trace_context('info', 'Root endpoint accessed', endpoint='/')
    return jsonify({
        "message": "Flask ToDo App - SigNoz Observability Stack",
        "endpoints": {
            "tasks": "/tasks",
            "health": "/health"
        },
        "observability": {
            "platform": "SigNoz",
            "traces": "enabled" if OTEL_ENABLED else "disabled",
            "metrics": "enabled" if OTEL_ENABLED else "disabled",
            "logs": "enabled" if OTEL_ENABLED else "disabled"
        }
    })

@app.route("/health", methods=["GET"])
def health():
    if OTEL_ENABLED:
        try:
            current_span = trace.get_current_span()
            if current_span:
                current_span.set_attribute("health.check", "ok")
                current_span.set_attribute("tasks.count", len(tasks))
        except:
            pass
    
    log_with_trace_context('info', 'Health check performed', 
                           status='healthy',
                           task_count=len(tasks))
    
    return jsonify({
        "status": "healthy",
        "service": "flask-todo",
        "tasks_count": len(tasks),
        "observability": {
            "tracing": "enabled" if OTEL_ENABLED else "disabled",
            "metrics": "enabled" if OTEL_ENABLED else "disabled",
            "logging": "enabled" if OTEL_ENABLED else "disabled",
            "platform": "SigNoz" if OTEL_ENABLED else "None"
        }
    }), 200

@app.route("/tasks", methods=["GET"])
def get_tasks():
    start_time = time.time()
    
    if OTEL_ENABLED:
        try:
            current_span = trace.get_current_span()
            with tracer.start_as_current_span("fetch_all_tasks") as span:
                span.set_attribute("task.count", len(tasks))
                task_list = list(tasks.values())
                log_with_trace_context('info', 'Fetching all tasks', task_count=len(task_list), operation='get_all')
                span.set_status(trace.Status(trace.StatusCode.OK))
            
            if current_span:
                current_span.set_attribute("response.task_count", len(task_list))
            
            duration = time.time() - start_time
            request_duration.record(duration, {"method": "GET", "endpoint": "/tasks", "status": "200"})
        except:
            task_list = list(tasks.values())
    else:
        task_list = list(tasks.values())
    
    return jsonify(task_list), 200

@app.route("/tasks", methods=["POST"])
def create_task():
    start_time = time.time()
    data = request.get_json()
    
    if not data or "task" not in data:
        log_with_trace_context('warning', 'Bad request - missing task field', error='missing_field', endpoint='/tasks')
        
        if OTEL_ENABLED:
            try:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", "missing_task_field")
                    current_span.set_status(trace.Status(trace.StatusCode.ERROR))
                error_counter.add(1, {"endpoint": "/tasks", "status": "400"})
                duration = time.time() - start_time
                request_duration.record(duration, {"method": "POST", "endpoint": "/tasks", "status": "400"})
            except:
                pass
        
        return jsonify({"error": "Missing 'task' field"}), 400
    
    task_id = len(tasks) + 1
    task_text = data["task"]
    
    tasks[task_id] = {
        "id": task_id,
        "task": task_text,
        "done": False
    }
    
    if OTEL_ENABLED:
        try:
            with tracer.start_as_current_span("create_task_operation") as span:
                span.set_attribute("task.id", task_id)
                span.set_attribute("task.text", task_text)
                span.set_attribute("operation", "create")
                span.set_status(trace.Status(trace.StatusCode.OK))
            
            task_counter.add(1)
            task_operations.add(1, {"operation": "create"})
            duration = time.time() - start_time
            request_duration.record(duration, {"method": "POST", "endpoint": "/tasks", "status": "201"})
        except:
            pass
    
    log_with_trace_context('info', 'Task created successfully', task_id=task_id, task_text=task_text, operation='create')
    
    return jsonify(tasks[task_id]), 201

@app.route("/tasks/<int:task_id>", methods=["GET"])
def get_task(task_id):
    if task_id not in tasks:
        if OTEL_ENABLED:
            try:
                error_counter.add(1, {"endpoint": "/tasks/id", "status": "404"})
            except:
                pass
        return jsonify({"error": "Task not found"}), 404
    
    return jsonify(tasks[task_id]), 200

@app.route("/tasks/<int:task_id>", methods=["PUT"])
def update_task(task_id):
    if task_id not in tasks:
        return jsonify({"error": "Task not found"}), 404
    
    data = request.get_json()
    if not data or "done" not in data:
        return jsonify({"error": "Missing 'done' field"}), 400
    
    tasks[task_id]["done"] = data["done"]
    
    if OTEL_ENABLED:
        try:
            task_operations.add(1, {"operation": "update"})
        except:
            pass
    
    return jsonify(tasks[task_id]), 200

@app.route("/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    if task_id not in tasks:
        return jsonify({"error": "Task not found"}), 404
    
    del tasks[task_id]
    
    if OTEL_ENABLED:
        try:
            task_operations.add(1, {"operation": "delete"})
        except:
            pass
    
    return jsonify({"message": "Task deleted"}), 200

# ============================================
# Main
# ============================================

if __name__ == "__main__":
    print("=" * 50, flush=True)
    print("🚀 Flask ToDo App Starting", flush=True)
    print(f"📊 Observability: {'ENABLED' if OTEL_ENABLED else 'DISABLED'}", flush=True)
    print(f"🌐 Port: 5000", flush=True)
    print("=" * 50, flush=True)
    
    app.run(host="0.0.0.0", port=5000, debug=False)