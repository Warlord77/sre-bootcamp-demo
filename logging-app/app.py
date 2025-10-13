from flask import Flask, request, jsonify
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import logging
import time

app = Flask(__name__)

# Configure logging to stdout (Docker will capture it)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Simple in-memory task storage
tasks = {}

# Prometheus Metrics
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP Requests",
    ["method", "endpoint", "http_status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_latency_seconds",
    "Request latency (seconds)",
    ["endpoint"],
)

@app.route("/tasks", methods=["GET", "POST"])
def task_list():
    start_time = time.time()
    method = request.method
    endpoint = "/tasks"
    status = 200

    try:
        if method == "GET":
            logger.info(f"Fetching all tasks, count: {len(tasks)}")
            resp = jsonify(list(tasks.values()))
            status = 200
        elif method == "POST":
            data = request.get_json()
            if not data or "task" not in data:
                status = 400
                logger.error("Missing 'task' field in POST request")
                REQUEST_COUNT.labels(method=method, endpoint=endpoint, http_status=status).inc()
                return jsonify({"error": "Missing 'task' field"}), 400
            
            task_id = len(tasks) + 1
            tasks[task_id] = {"id": task_id, "task": data["task"], "done": False}
            logger.info(f"Created task {task_id}: {data['task']}")
            resp = jsonify(tasks[task_id])
            status = 201
        
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, http_status=status).inc()
        REQUEST_LATENCY.labels(endpoint=endpoint).observe(time.time() - start_time)
        resp.status_code = status
        return resp

    except Exception as e:
        status = 500
        logger.error(f"Error in {method} {endpoint}: {str(e)}")
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, http_status=status).inc()
        REQUEST_LATENCY.labels(endpoint=endpoint).observe(time.time() - start_time)
        return jsonify({"error": "Internal Server Error"}), 500

@app.route("/tasks/<int:task_id>", methods=["PUT", "DELETE"])
def task_modify(task_id):
    start_time = time.time()
    method = request.method
    endpoint = "/tasks/id"
    status = 200

    try:
        if task_id not in tasks:
            status = 404
            logger.warning(f"Task {task_id} not found")
            REQUEST_COUNT.labels(method=method, endpoint=endpoint, http_status=status).inc()
            REQUEST_LATENCY.labels(endpoint=endpoint).observe(time.time() - start_time)
            return jsonify({"error": "Task not found"}), 404

        if method == "PUT":
            data = request.get_json()
            if not data or "done" not in data:
                status = 400
                logger.error(f"Missing 'done' field in PUT request for task {task_id}")
                REQUEST_COUNT.labels(method=method, endpoint=endpoint, http_status=status).inc()
                REQUEST_LATENCY.labels(endpoint=endpoint).observe(time.time() - start_time)
                return jsonify({"error": "Missing 'done' field"}), 400
            
            tasks[task_id]["done"] = data["done"]
            logger.info(f"Updated task {task_id}: done={data['done']}")
            resp = jsonify(tasks[task_id])
            status = 200

        elif method == "DELETE":
            deleted_task = tasks[task_id]["task"]
            del tasks[task_id]
            logger.info(f"Deleted task {task_id}: {deleted_task}")
            resp = jsonify({"message": "Task deleted"})
            status = 200

        REQUEST_COUNT.labels(method=method, endpoint=endpoint, http_status=status).inc()
        REQUEST_LATENCY.labels(endpoint=endpoint).observe(time.time() - start_time)
        resp.status_code = status
        return resp

    except Exception as e:
        status = 500
        logger.error(f"Error in {method} /tasks/{task_id}: {str(e)}")
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, http_status=status).inc()
        REQUEST_LATENCY.labels(endpoint=endpoint).observe(time.time() - start_time)
        return jsonify({"error": "Internal Server Error"}), 500

@app.route("/metrics")
def metrics():
    logger.info("Metrics endpoint accessed")
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}

@app.route("/")
def index():
    logger.info("Root endpoint accessed")
    return jsonify({"message": "Flask ToDo App with Prometheus + Loki"})

@app.errorhandler(404)
def not_found(error):
    logger.warning(f"404 error: {request.path}")
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 error: {str(error)}")
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    logger.info("Starting Flask ToDo App on port 5000...")
    app.run(host="0.0.0.0", port=5000)