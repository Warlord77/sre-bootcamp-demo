#!/bin/bash
curl -s http://localhost:8000/tasks | jq

# 2. Add a task "Buy milk"
curl -s -X POST http://localhost:8000/tasks \
     -H "Content-Type: application/json" \
     -d '{"task":"Buy milk"}' | jq

# 3. Add another task "Do homework"
curl -s -X POST http://localhost:8000/tasks \
     -H "Content-Type: application/json" \
     -d '{"task":"Do homework"}' | jq

# 4. Get all tasks again (now should show 2 tasks with IDs)
curl -s http://localhost:8000/tasks | jq

# 5. Update task ID=1 → mark it done
curl -s -X PUT http://localhost:8000/tasks/1 \
     -H "Content-Type: application/json" \
     -d '{"done": true}' | jq

# 6. Update task ID=2 → rename it
curl -s -X PUT http://localhost:8000/tasks/2 \
     -H "Content-Type: application/json" \
     -d '{"task": "Do math homework"}' | jq

# 7. Get all tasks to see updates
curl -s http://localhost:8000/tasks | jq

# 8. Delete task ID=1
#curl -s -X DELETE http://localhost:8000/tasks/1 | jq

# 9. Get all tasks again (should only show task ID=2)
curl -s http://localhost:8000/tasks | jq
