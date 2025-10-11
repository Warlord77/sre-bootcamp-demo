#!/bin/bash
BASE_URL="http://localhost:8000"

echo "Generating traces + logs + metrics..."

# create tasks
for i in {1..5}; do
  curl -s -X POST "$BASE_URL/tasks" -H "Content-Type: application/json" -d "{\"task\":\"Task $i\"}" > /dev/null
  sleep 0.2
done

# read tasks repeatedly
for i in {1..10}; do
  curl -s "$BASE_URL/tasks" > /dev/null
  sleep 0.1
done

# update some tasks
for i in 1 2 3; do
  curl -s -X PUT "$BASE_URL/tasks/$i" -H "Content-Type: application/json" -d '{"done": true}' > /dev/null
  sleep 0.1
done

# hit invalid endpoint to trigger 500/404 logs (depending on handler)
for i in {1..3}; do
  curl -s "$BASE_URL/invalid-endpoint" > /dev/null
  sleep 0.1
done

echo "Done."
