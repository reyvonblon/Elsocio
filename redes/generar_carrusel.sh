#!/bin/bash
# Genera un carrusel de Instagram (láminas 1080x1350) vía Remotion + SwiftShader en Monterey.
# Uso: ./generar_carrusel.sh '{"laminas":["portada","idea","idea","cierre"],"badge":"CONFECCIÓN","tema":"oscuro"}' nombre_salida
# Salida: redes/carruseles/<nombre>_01.png, <nombre>_02.png, ... (una por lámina, en orden)

set -e
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"

PROPS="$1"
NOMBRE="${2:-carrusel_$(date +%s)}"

if [ -z "$PROPS" ]; then
  echo "Uso: ./generar_carrusel.sh '{\"laminas\":[...]}' [nombre_salida]"
  exit 1
fi

cd "$(dirname "$0")"
mkdir -p carruseles

cd video-logo
TMP_DIR="out/frames_carrusel_$$"
trap 'rm -rf "$TMP_DIR"' EXIT
rm -rf "$TMP_DIR"

# Un frame = una lámina: un solo render saca todo el carrusel.
npx remotion render CarruselLaminas "$TMP_DIR" \
  --sequence \
  --image-format=png \
  --props="$PROPS" \
  --browser-executable="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --is-production=false \
  --gl=swiftshader \
  --concurrency=1

N=0
rm -f "../carruseles/${NOMBRE}"_[0-9][0-9].png
for FRAME in $(ls "$TMP_DIR"/*.png 2>/dev/null | sort); do
  N=$((N + 1))
  mv -f "$FRAME" "../carruseles/${NOMBRE}_$(printf '%02d' "$N").png"
done

if [ "$N" -lt 2 ]; then
  echo "Error: Remotion no generó las láminas del carrusel" >&2
  exit 1
fi

echo "Listo: redes/carruseles/${NOMBRE}_01.png … $(printf '%02d' "$N") ($N láminas)"
