#!/bin/bash
# Genera una imagen vertical 1080x1920 para Historias de IG (vía Remotion + SwiftShader en Monterey).
# Uso: ./generar_historia.sh "Gancho" [nombre_salida] ["Subtexto"] ["Cierre"] ["Badge"] ["oscuro|crema"]

set -e
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"

GANCHO="$1"
NOMBRE="${2:-historia_$(date +%s)}"
SUBTEXTO="${3:-}"
CIERRE="${4:-Responde esta historia con tu caso}"
BADGE="${5:-HISTORIA}"
TEMA="${6:-oscuro}"

if [ -z "$GANCHO" ]; then
  echo "Uso: ./generar_historia.sh \"Gancho\" [nombre_salida] [subtexto] [cierre] [badge] [tema]"
  exit 1
fi

cd "$(dirname "$0")"
mkdir -p historias

PROPS=$(python3 -c "
import json, sys
tema = 'crema' if sys.argv[5].strip().lower() == 'crema' else 'oscuro'
print(json.dumps({
    'gancho': sys.argv[1],
    'subtexto': sys.argv[2],
    'cierre': sys.argv[3],
    'badge': sys.argv[4],
    'tema': tema,
}, ensure_ascii=False))
" "$GANCHO" "$SUBTEXTO" "$CIERRE" "$BADGE" "$TEMA")

cd video-logo
TMP_DIR="out/frames_hist_$$"
trap 'rm -rf "$TMP_DIR"' EXIT
rm -rf "$TMP_DIR"

npx remotion render HistoriaVertical "$TMP_DIR" \
  --sequence \
  --frames=0-0 \
  --image-format=png \
  --props="$PROPS" \
  --browser-executable="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --is-production=false \
  --gl=swiftshader \
  --concurrency=1

FRAME_GEN=$(ls "$TMP_DIR"/*.png 2>/dev/null | head -1)
if [ -z "$FRAME_GEN" ]; then
  echo "Error: Remotion no generó la imagen de historia" >&2
  exit 1
fi

mv -f "$FRAME_GEN" "../historias/${NOMBRE}.png"
echo "Listo: redes/historias/${NOMBRE}.png"
