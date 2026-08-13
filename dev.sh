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

# 이전 세션이 비정상 종료(터미널 강제 종료 등)되면 uvicorn --reload / vite 프로세스가 orphan으로
# 남아 포트(및 DB 커넥션)를 계속 점유할 수 있음 — 재기동 전 포트 선점 프로세스 정리
kill_port() {
  local port="$1"
  local label="$2"
  local pids
  pids=$(powershell.exe -NoProfile -Command \
    "(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue).OwningProcess" \
    2>/dev/null | tr -d '\r')
  if [ -n "$pids" ]; then
    echo "${port} 포트(${label})를 점유 중인 이전 프로세스 발견, 종료합니다: $pids"
    for pid in $pids; do
      powershell.exe -NoProfile -Command "Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue" 2>/dev/null
    done
    sleep 1
  fi
}
kill_port 8000 "백엔드"
kill_port 5173 "프론트엔드"

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
