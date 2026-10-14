#!/usr/bin/env bash
# Publica los prototipos con un túnel rápido de Cloudflare y muestra el enlace con su clave.
#   bash prototypes/movil/tunnel.sh          # arranca (o reutiliza) el servidor y abre un túnel nuevo
# El enlace cambia cada vez que se abre un túnel nuevo; la clave se conserva en ~/.cryptoreport-propuestas-token.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${PORT:-8741}"
LOG_DIR="${LOG_DIR:-/tmp/cryptoreport-propuestas}"
mkdir -p "$LOG_DIR"

if ! curl -s -o /dev/null "http://127.0.0.1:$PORT/"; then
  nohup python3 "$DIR/serve.py" "$PORT" > "$LOG_DIR/serve.log" 2>&1 &
  for _ in $(seq 1 20); do curl -s -o /dev/null "http://127.0.0.1:$PORT/" && break; sleep 0.5; done
fi

pkill -f "cloudflared tunnel --url http://127.0.0.1:$PORT " 2>/dev/null || true
: > "$LOG_DIR/tunnel.log"
nohup cloudflared tunnel --url "http://127.0.0.1:$PORT" --no-autoupdate > "$LOG_DIR/tunnel.log" 2>&1 &

URL=""
for _ in $(seq 1 40); do
  URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG_DIR/tunnel.log" | head -1 || true)
  [ -n "$URL" ] && break
  sleep 1
done
[ -n "$URL" ] || { echo "No se obtuvo la URL del túnel; revisa $LOG_DIR/tunnel.log" >&2; exit 1; }
TOKEN=$(tr -d '\n' < "${CR_PROTO_TOKEN_FILE:-$HOME/.cryptoreport-propuestas-token}")
echo "$URL/?k=$TOKEN"
