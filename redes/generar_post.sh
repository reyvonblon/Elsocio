#!/bin/bash
# Genera una imagen de post para IG (fondo negro + frase + logo, 1080x1350).
# Uso: ./generar_post.sh "La frase del post" nombre_salida

set -e

FRASE="$1"
NOMBRE="${2:-post_$(date +%s)}"

if [ -z "$FRASE" ]; then
  echo "Uso: ./generar_post.sh \"Frase del post\" [nombre_salida]"
  exit 1
fi

cd "$(dirname "$0")"
mkdir -p posts

PORT=8891
if ! lsof -i ":$PORT" >/dev/null 2>&1; then
  (python3 -m http.server "$PORT" >/tmp/el_socio_redes_server.log 2>&1 &)
  sleep 1
fi

ENCODED=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$FRASE")

"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless --disable-gpu \
  --user-data-dir="$(mktemp -d)" \
  --no-first-run --no-default-browser-check \
  --screenshot="posts/${NOMBRE}.png" \
  --window-size=1080,1350 \
  "http://localhost:${PORT}/plantilla_post.html?frase=${ENCODED}"

echo "Listo: redes/posts/${NOMBRE}.png"
