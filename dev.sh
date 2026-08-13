#!/usr/bin/env bash
set -uo pipefail

# --keep-port: 백엔드 8000 포트가 이미 사용 중이면 강제 종료하는 대신
# 비어있는 다음 포트로 대신 구동 (다른 세션이 의도적으로 띄워둔 백엔드를 보존)
KEEP_PORT=0
for _arg in "$@"; do
  case "$_arg" in
    --keep-port) KEEP_PORT=1 ;;
  esac
done
unset _arg

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
port_owner_pids() {
  local port="$1"
  powershell.exe -NoProfile -Command \
    "(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue).OwningProcess" \
    2>/dev/null | tr -d '\r'
}

is_port_busy() {
  [ -n "$(port_owner_pids "$1")" ]
}

find_free_port() {
  local port="$1"
  while is_port_busy "$port"; do
    port=$((port + 1))
  done
  echo "$port"
}

kill_port() {
  local port="$1"
  local label="$2"
  local pids
  pids=$(port_owner_pids "$port")
  if [ -n "$pids" ]; then
    echo "${port} 포트(${label})를 점유 중인 이전 프로세스 발견, 종료합니다: $pids"
    for pid in $pids; do
      powershell.exe -NoProfile -Command "Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue" 2>/dev/null
    done
    sleep 1
  fi
}

BACKEND_PORT=8000
if [ "$KEEP_PORT" -eq 1 ]; then
  if is_port_busy "$BACKEND_PORT"; then
    BACKEND_PORT=$(find_free_port $((BACKEND_PORT + 1)))
    echo "8000 포트가 이미 사용 중 — 기존 프로세스를 유지하고 백엔드를 ${BACKEND_PORT} 포트로 대신 구동합니다."
  fi
else
  kill_port 8000 "백엔드"
fi
kill_port 5173 "프론트엔드"

(cd backend && .venv/Scripts/uvicorn app.main:app --reload --port "$BACKEND_PORT") &
BACKEND_PID=$!

echo "백엔드 시작 대기 중... (포트 ${BACKEND_PORT})"
for i in $(seq 1 20); do
  if curl -s "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

export VITE_DEV_BACKEND_PORT="$BACKEND_PORT"
(cd frontend && npm run dev) &
FRONTEND_PID=$!

cleanup() {
  echo ""
  echo "서버 종료 중..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

echo "백엔드:    http://localhost:${BACKEND_PORT}"
echo "프론트엔드: http://localhost:5173"
echo "Ctrl+C로 두 서버 모두 종료됩니다."

wait "$BACKEND_PID" "$FRONTEND_PID"
