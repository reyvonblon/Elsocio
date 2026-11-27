#!/bin/bash
# Renderiza un capítulo del reel en pixel art y lo arma en mp4.
#   ./redes/generar_reel_pixel.sh <capitulo>   (taller | obra | azotea)
# Sin voz: el saldo de IA está agotado. Los subtítulos van cronometrados como si se hablara,
# así que el ritmo se juzga igual.
set -e
CAP="${1:-taller}"
cd "$(dirname "$0")/video-logo"
SALIDA="out/pixel/reel_${CAP}.mp4"
FRAMES="out/frames_pixel_${CAP}"

rm -rf "$FRAMES"
npx remotion render ReelPixel "$FRAMES" \
  --sequence --image-format=png \
  --props="{\"capitulo\":\"$CAP\"}" \
  --browser-executable="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --gl=swiftshader --concurrency=1 --is-production=false

PRIMERO=$(ls "$FRAMES"/*.png | head -1)
BASE=$(basename "$PRIMERO" .png)
PREFIJO="${BASE%-*}"
DIGITOS=$(( ${#BASE} - ${#PREFIJO} - 1 ))

# crf bajo: el pixel art se arruina si el códec le suaviza los bordes
ffmpeg -y -loglevel error -framerate 30 \
  -i "$FRAMES/${PREFIJO}-%0${DIGITOS}d.png" \
  -c:v libx264 -preset medium -crf 17 -pix_fmt yuv420p \
  -movflags +faststart "$SALIDA"

rm -rf "$FRAMES"
echo "listo: $SALIDA"
