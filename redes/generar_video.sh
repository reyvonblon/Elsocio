#!/bin/bash
# Genera un video vertical para IG (fondo negro, paleta de El Socio).
# Uso:
#   ./generar_video.sh "La frase del video" nombre_salida                 # LogoFrase 1080x1350
#   ./generar_video.sh --reel '{"gancho":"...","bloques":["a","b"],"cierre":"..."}' nombre  # 1080x1920
#
# Por qué existe: en este Mac (macOS Monterey) el render de video nativo de
# Remotion falla porque su compositor exige macOS 15 (Sequoia). La solución es
# pedirle a Remotion solo los frames PNG (eso sí funciona) y unirlos con el
# ffmpeg del sistema, que es independiente y ya está instalado.

set -e

# Asegurar que /usr/local/bin esté en PATH cuando corra desde launchd en segundo plano.
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"

CON_VOZ=1
ARGS=()
for arg in "$@"; do
  if [ "$arg" = "--sin-voz" ]; then
    CON_VOZ=0
  else
    ARGS+=("$arg")
  fi
done
set -- "${ARGS[@]}"

if [ "$1" = "--reel" ]; then
  COMPOSICION="ReelVertical"
  PROPS="$2"
  NOMBRE="${3:-reel_$(date +%s)}"
  if [ -z "$PROPS" ]; then
    echo "Uso: ./generar_video.sh --reel '{\"gancho\":\"...\",\"bloques\":[...],\"cierre\":\"...\"}' [nombre] [--sin-voz]"
    exit 1
  fi
else
  COMPOSICION="LogoFrase"
  FRASE="$1"
  NOMBRE="${2:-video_$(date +%s)}"
  CON_VOZ=0
  if [ -z "$FRASE" ]; then
    echo "Uso: ./generar_video.sh \"Frase del video\" [nombre_salida]"
    exit 1
  fi
  PROPS=$(node -e "console.log(JSON.stringify({frase: process.argv[1]}))" "$FRASE")
fi

cd "$(dirname "$0")/video-logo"
mkdir -p out

PISTA_VOZ=""
PROPS_SYNC="out/${NOMBRE}_props.json"
rm -f "$PROPS_SYNC" "out/${NOMBRE}_voz.m4a"

if [ "$CON_VOZ" = "1" ] && [ "$COMPOSICION" = "ReelVertical" ]; then
  if python3 ../../scripts/voice_engine.py \
      --reel-props "$PROPS" \
      --out "out/${NOMBRE}_voz.m4a" \
      --out-props "$PROPS_SYNC"; then
    PISTA_VOZ="out/${NOMBRE}_voz.m4a"
    PROPS=$(cat "$PROPS_SYNC")
    echo "Voz humana sincronizada lista: ${PISTA_VOZ}"
  else
    echo "Aviso: no se pudo generar locución neuronal (red no disponible); se continúa sin pista de voz." >&2
  fi
fi

rm -rf out/frames
npx remotion render "$COMPOSICION" out/frames \
  --sequence \
  --image-format=png \
  --props="$PROPS" \
  --browser-executable="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --is-production=false \
  --gl=swiftshader \
  --concurrency=1

# Remotion elige el relleno de ceros según la duración de la composición (3 dígitos
# para videos cortos, 4 o más para largos). Fijarlo a mano fue el bug que cortaba
# los videos en 33 s: aquí se detecta del primer frame real, así nunca vuelve a pasar.
PRIMER_FRAME=$(ls out/frames/*.png 2>/dev/null | head -1)
if [ -z "$PRIMER_FRAME" ]; then
  echo "Error: Remotion no generó ningún frame en out/frames/" >&2
  exit 1
fi
BASE=$(basename "$PRIMER_FRAME" .png)      # ej. element-0001
PREFIJO="${BASE%-*}"                        # ej. element
DIGITOS=${#BASE}
DIGITOS=$((DIGITOS - ${#PREFIJO} - 1))      # cuántos dígitos trae de verdad
PATRON="out/frames/${PREFIJO}-%0${DIGITOS}d.png"
echo "Frames: $(ls out/frames/*.png | wc -l | tr -d ' ') · patrón detectado: ${PATRON}"

if [ -n "$PISTA_VOZ" ] && [ -f "$PISTA_VOZ" ]; then
  ffmpeg -y -framerate 30 -start_number 0 -i "$PATRON" -i "$PISTA_VOZ" \
    -c:v libx264 -pix_fmt yuv420p -c:a copy -movflags +faststart \
    "out/${NOMBRE}.mp4" 2>/dev/null \
  || ffmpeg -y -framerate 30 -start_number 1 -i "$PATRON" -i "$PISTA_VOZ" \
    -c:v libx264 -pix_fmt yuv420p -c:a copy -movflags +faststart \
    "out/${NOMBRE}.mp4"
else
  ffmpeg -y -framerate 30 -start_number 0 -i "$PATRON" \
    -c:v libx264 -pix_fmt yuv420p -movflags +faststart \
    "out/${NOMBRE}.mp4" 2>/dev/null \
  || ffmpeg -y -framerate 30 -start_number 1 -i "$PATRON" \
    -c:v libx264 -pix_fmt yuv420p -movflags +faststart \
    "out/${NOMBRE}.mp4"
fi

rm -rf out/frames "$PROPS_SYNC" "$PISTA_VOZ"
echo "Listo: redes/video-logo/out/${NOMBRE}.mp4"
