#!/bin/bash
# Genera un video de logo animado + frase para IG (fondo negro, 1080x1350).
# Uso: ./generar_video.sh "La frase que va en el video" nombre_salida
#
# Por qué existe: en este Mac (macOS Monterey) el render de video nativo de
# Remotion falla porque su compositor exige macOS 15 (Sequoia). La solución es
# pedirle a Remotion solo los frames PNG (eso sí funciona) y unirlos con el
# ffmpeg del sistema, que es independiente y ya está instalado.

set -e

FRASE="$1"
NOMBRE="${2:-video_$(date +%s)}"

if [ -z "$FRASE" ]; then
  echo "Uso: ./generar_video.sh \"Frase del video\" [nombre_salida]"
  exit 1
fi

cd "$(dirname "$0")/video-logo"

PROPS=$(node -e "console.log(JSON.stringify({frase: process.argv[1]}))" "$FRASE")

rm -rf out/frames
npx remotion render LogoFrase out/frames \
  --sequence \
  --image-format=png \
  --props="$PROPS" \
  --browser-executable="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --is-production=false \
  --gl=swiftshader \
  --concurrency=1

ffmpeg -y -framerate 30 -i out/frames/element-%03d.png \
  -c:v libx264 -pix_fmt yuv420p -movflags +faststart \
  "out/${NOMBRE}.mp4"

rm -rf out/frames
echo "Listo: redes/video-logo/out/${NOMBRE}.mp4"
