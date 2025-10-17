BASE_URL="http://localhost:8000"

echo "🚀 Generating load for Flask ToDo app with full observability..."
echo ""

# Health check first
echo "1️⃣  Health Check"
curl -s "$BASE_URL/health" | jq .
echo ""
sleep 1

# Add 10 tasks
echo "2️⃣  Creating 10 tasks..."
for i in {1..10}; do
  response=$(curl -s -X POST "$BASE_URL/tasks" \
       -H "Content-Type: application/json" \
       -d "{\"task\":\"Task $i - Buy groceries item $i\"}")
  echo "   Created: Task $i"
  sleep 0.3
done
echo ""

# Fetch tasks multiple times
echo "3️⃣  Fetching all tasks (5 times)..."
for i in {1..5}; do
  count=$(curl -s "$BASE_URL/tasks" | jq '. | length')
  echo "   Fetch $i: Found $count tasks"
  sleep 0.2
done
echo ""

# Update some tasks
echo "4️⃣  Updating tasks 1-5 to done=true..."
for i in {1..5}; do
  curl -s -X PUT "$BASE_URL/tasks/$i" \
       -H "Content-Type: application/json" \
       -d '{"done": true}' > /dev/null
  echo "   Updated: Task $i"
  sleep 0.2
done
echo ""

# Get individual tasks
echo "5️⃣  Getting individual tasks..."
for i in {1..3}; do
  task=$(curl -s "$BASE_URL/tasks/$i" | jq -r '.task')
  echo "   Task $i: $task"
  sleep 0.2
done
echo ""

# Delete some tasks
echo "6️⃣  Deleting tasks 6-8..."
for i in {6..8}; do
  curl -s -X DELETE "$BASE_URL/tasks/$i" > /dev/null
  echo "   Deleted: Task $i"
  sleep 0.2
done
echo ""

# Trigger 404s
echo "7️⃣  Triggering errors (404s)..."
for i in {1..3}; do
  curl -s "$BASE_URL/invalid-endpoint-$i" > /dev/null
  echo "   404: /invalid-endpoint-$i"
  sleep 0.2
done
echo ""

# Trigger 404 for non-existent task
echo "8️⃣  Trying to update non-existent task..."
curl -s -X PUT "$BASE_URL/tasks/9999" \
     -H "Content-Type: application/json" \
     -d '{"done": true}' > /dev/null
echo "   404: Task 9999 not found"
echo ""

# Final stats
echo "9️⃣  Final Statistics:"
task_count=$(curl -s "$BASE_URL/tasks" | jq '. | length')
echo "   Total tasks remaining: $task_count"
echo ""

echo "✅ Load generation complete!"
echo ""


echo "═══════════════════════════════════════════════════════"
echo "📊 View Observability Data:"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "🔍 TRACES (Jaeger):"
echo "   URL: http://localhost