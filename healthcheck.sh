#!/usr/bin/env bash
# NXT Reel AI - quick health check before running a new test
echo "================================================"
echo " NXT Reel AI Health Check — $(date)"
echo "================================================"

echo ""
echo "--- 1. Container status ---"
docker compose ps

echo ""
echo "--- 2. Disk space ---"
df -h / | tail -1

echo ""
echo "--- 3. Backend health endpoint ---"
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://reel.nxtautomation.online/api/health

echo ""
echo "--- 4. Projects endpoint (should list your projects, not error) ---"
curl -s https://reel.nxtautomation.online/api/projects | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(f'OK — {len(data)} project(s) found')
except Exception as e:
    print(f'FAILED TO PARSE: {e}')
"

echo ""
echo "--- 5. Backend logs — last 15 lines (look for tracebacks) ---"
docker compose logs backend --tail=15

echo ""
echo "--- 6. Worker logs — last 15 lines (look for tracebacks) ---"
docker compose logs worker --tail=15

echo ""
echo "--- 7. Python syntax check on recently edited files ---"
for f in \
    backend/app/ai/agents/visual_director.py \
    backend/app/ai/agents/orchestrator.py \
    backend/app/ai/agents/creative_director.py \
    backend/app/ai/validator.py \
    backend/app/ai/transcription.py \
    backend/app/services/render_service.py \
    backend/app/main.py
do
    result=$(python3 -c "import ast; ast.parse(open('$f').read())" 2>&1)
    if [ -z "$result" ]; then
        echo "OK   — $f"
    else
        echo "FAIL — $f"
        echo "       $result"
    fi
done

echo ""
echo "--- 8. Nginx status ---"
sudo systemctl is-active nginx

echo ""
echo "--- 9. Certbot cert expiry ---"
sudo certbot certificates 2>/dev/null | grep -A2 "reel.nxtautomation.online"

echo ""
echo "================================================"
echo " Health check complete"
echo "================================================"
