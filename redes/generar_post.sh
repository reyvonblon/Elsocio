#!/bin/bash
# Genera una imagen de post 1080x1350 para IG (vía Remotion + SwiftShader en Monterey).
# Uso: ./generar_post.sh "La frase del post" nombre_salida

set -e
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"

FRASE="$1"
NOMBRE="${2:-post_$(date +%s)}"

if [ -z "$FRASE" ]; then
  echo "Uso: ./generar_post.sh \"Frase del post\" [nombre_salida]"
  exit 1
fi

cd "$(dirname "$0")"
mkdir -p posts

PROPS=$(python3 -c "import json, sys; print(json.dumps({'frase': sys.argv[1]}, ensure_ascii=False))" "$FRASE")

cd video-logo
TMP_DIR="out/frames_post_$$"
trap 'rm -rf "$TMP_DIR"' EXIT
rm -rf "$TMP_DIR"

npx remotion render LogoFrase "$TMP_DIR" \
  --sequence \
  --frames=45-45 \
  --image-format=png \
  --props="$PROPS" \
  --browser-executable="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --is-production=false \
  --gl=swiftshader \
  --concurrency=1

FRAME_GEN=$(ls "$TMP_DIR"/*.png 2>/dev/null | head -1)
if [ -z "$FRAME_GEN" ]; then
  echo "Error: Remotion no generó la imagen del post" >&2
  exit 1
fi

mv -f "$FRAME_GEN" "../posts/${NOMBRE}.png"
echo "Listo: redes/posts/${NOMBRE}.png"
