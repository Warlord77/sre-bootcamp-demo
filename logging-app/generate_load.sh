#!/bin/bash

BASE_URL="http://localhost:8000"

echo "🚀 Generating load for Flask ToDo app..."

# Add 10 tasks
for i in {1..10}; do
  curl -s -X POST "$BASE_URL/tasks" \
       -H "Content-Type: application/json" \
       -d "{\"task\":\"Task $i\"}" > /dev/null
  sleep 0.2
done

# Fetch tasks multiple times
for i in {1..5}; do
  curl -s "$BASE_URL/tasks" > /dev/null
  sleep 0.2
done

# Update some tasks
for i in {1..5}; do
  curl -s -X PUT "$BASE_URL/tasks/$i" \
       -H "Content-Type: application/json" \
       -d '{"done": true}' > /dev/null
  sleep 0.2
done

# Delete some tasks
for i in {6..8}; do
  curl -s -X DELETE "$BASE_URL/tasks/$i" > /dev/null
  sleep 0.2
done

# Trigger some errors (invalid endpoint = 404, should log warnings)
for i in {1..3}; do
  curl -s "$BASE_URL/invalid-endpoint" > /dev/null
  sleep 0.2
done

# Trigger DB error by updating invalid task ID
curl -s -X PUT "$BASE_URL/tasks/9999" \
     -H "Content-Type: application/json" \
     -d '{"done": true}' > /dev/null

echo "✅ Load generation complete."
echo "👉 Check Grafana Loki datasource for logs from container {container=\"flask-todo\"}"
