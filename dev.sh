#!/usr/bin/env bash
set -uo pipefail

# Windows Git Bash: Node.js PATH 보장
for _NODE_DIR in \
  "/c/Program Files/nodejs" \
  "$APPDATA/nvm" \
  "$HOME/AppData/Roaming/nvm" \
  "$HOME/.volta/bin" \
  "$HOME/.fnm"; do
  if command -v npm &>/dev/null; then
    break
  elif [ -d "$_NODE_DIR" ]; then
    export PATH="$_NODE_DIR:$PATH"
  fi
done
unset _NODE_DIR

if [ ! -f "backend/.venv/Scripts/uvicorn" ]; then
  echo "오류: backend/.venv가 없습니다. 먼저 'make install-backend'를 실행하세요."
  exit 1
fi

(cd backend && .venv/Scripts/uvicorn app.main:app --reload) &
BACKEND_PID=$!

echo "백엔드 시작 대기 중..."
for i in $(seq 1 20); do
  if curl -s http://127.0.0.1:8000/health >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

(cd frontend && npm run dev) &
FRONTEND_PID=$!

cleanup() {
  echo ""
  echo "서버 종료 중..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

echo "백엔드:    http://localhost:8000"
echo "프론트엔드: http://localhost:5173"
echo "Ctrl+C로 두 서버 모두 종료됩니다."

wait "$BACKEND_PID" "$FRONTEND_PID"
