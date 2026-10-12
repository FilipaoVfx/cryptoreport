#!/usr/bin/env bash
# Instala o actualiza el sitio del pipeline: compila el CSS, copia la página, configura nginx y exporta data.json.
# La primera vez crea el usuario de acceso (contraseña en /root/.cryptoreport-site-password).
# HTTPS (una sola vez): certbot --nginx -d cryptoreport.2-25-233-186.sslip.io
set -euo pipefail
cd "$(dirname "$0")/.."
WWW=/var/www/cryptoreport
mkdir -p "$WWW"
(cd site && npx --yes tailwindcss@3.4.17 -c tailwind.config.js -i tailwind.css -o "$WWW/site.css" --minify)
install -m 644 site/index.html "$WWW/index.html"

if [ ! -f /etc/nginx/cryptoreport.htpasswd ]; then
  umask 077
  pass=$(openssl rand -base64 18 | tr -dc 'A-Za-z0-9' | head -c 20)
  printf 'crypto:%s\n' "$(openssl passwd -apr1 "$pass")" > /etc/nginx/cryptoreport.htpasswd
  printf 'usuario: crypto\ncontraseña: %s\n' "$pass" > /root/.cryptoreport-site-password
  chown root:www-data /etc/nginx/cryptoreport.htpasswd && chmod 640 /etc/nginx/cryptoreport.htpasswd
  echo "Acceso creado: ver /root/.cryptoreport-site-password"
fi

# Si certbot ya añadió HTTPS al archivo instalado, no lo pisamos.
if ! grep -q "managed by Certbot" /etc/nginx/sites-available/cryptoreport 2>/dev/null; then
  install -m 644 ops/nginx-cryptoreport.conf /etc/nginx/sites-available/cryptoreport
fi
ln -sf /etc/nginx/sites-available/cryptoreport /etc/nginx/sites-enabled/cryptoreport
nginx -t
systemctl reload nginx
.venv/bin/python -m crtranscripts site
