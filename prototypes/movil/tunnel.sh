#!/usr/bin/env bash
# Publica los prototipos con un túnel rápido de Cloudflare y muestra el enlace público.
#   bash prototypes/movil/tunnel.sh          # arranca (o reutiliza) el servidor y abre un túnel nuevo
# El enlace cambia cada vez que se abre un túnel nuevo; funciona sin claves ni cookies.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${PORT:-8741}"
LOG_DIR="${LOG_DIR:-/tmp/cryptoreport-propuestas}"

# En el VPS, reutilizar los servicios que arrancan con el sistema. No matar
# su túnel al volver a pedir la URL: perdería la dirección pública vigente.
if [ "$PORT" = 8741 ] && systemctl cat cryptoreport-urania-tunnel.service >/dev/null 2>&1; then
  systemctl start cryptoreport-urania-web.service cryptoreport-urania-tunnel.service
  for _ in $(seq 1 40); do
    INVOCATION=$(systemctl show cryptoreport-urania-tunnel.service -p InvocationID --value)
    URL=$(journalctl -u cryptoreport-urania-tunnel.service "_SYSTEMD_INVOCATION_ID=$INVOCATION" --no-pager -o cat |
      python3 -c 'import re,sys; urls=re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com",sys.stdin.read()); print(urls[-1] if urls else "")')
    if [ -n "$URL" ]; then echo "$URL/"; exit 0; fi
    sleep 1
  done
  echo "El servicio no publicó una URL; revisa journalctl -u cryptoreport-urania-tunnel.service" >&2
  exit 1
fi
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
echo "$URL/"
