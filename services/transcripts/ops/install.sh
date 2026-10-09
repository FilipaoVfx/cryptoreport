#!/usr/bin/env bash
# Instala o actualiza las unidades de systemd del servicio de transcripciones.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -x .venv/bin/python ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
[ -f .env ] || { echo "Falta .env (ver .env.example)" >&2; exit 1; }
chmod 600 .env
cp ops/cryptoreport-transcripts.service ops/cryptoreport-transcripts.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now cryptoreport-transcripts.timer
systemctl list-timers cryptoreport-transcripts.timer --no-pager
