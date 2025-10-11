#!/bin/bash

BASE_URL="http://localhost:8000"

echo "🚀 Generating load on Flask ToDo app..."

# Add tasks
for i in {1..10}; do
  curl -s -X POST $BASE_URL/tasks \
       -H "Content-Type: application/json" \
       -d "{\"task\":\"Task $i\"}" > /dev/null
done

# Get tasks repeatedly
for i in {1..20}; do
  curl -s $BASE_URL/tasks > /dev/null
done

# Update tasks
for i in {1..5}; do
  curl -s -X PUT $BASE_URL/tasks/$i \
       -H "Content-Type: application/json" \
       -d '{"done": true}' > /dev/null
done

# Force some 5xx errors by hitting invalid endpoints
for i in {1..5}; do
  curl -s $BASE_URL/invalid-endpoint > /dev/null
done

echo "✅ Load test complete. Check Grafana on http://localhost:3000"
