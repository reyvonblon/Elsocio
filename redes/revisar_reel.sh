#!/bin/bash
# Control de calidad de un reel YA renderizado, antes de aprobarlo para publicar.
#
# Uso:
#   ./revisar_reel.sh redes/video-logo/out/content_0007.mp4
#
# Saca una hoja de contacto (1 fotograma cada 0.5 s) junto al video: <nombre>_revision.jpg
# Con esa hoja se aplica el checklist de `contexto/director-de-video.md`:
# cada frase en pantalla tiene que mostrar el objeto que nombra, nada estático más de 3 s,
# ningún tramo con escena vacía.

set -e
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"

VIDEO="$1"
if [ -z "$VIDEO" ] || [ ! -f "$VIDEO" ]; then
  echo "Uso: ./revisar_reel.sh video.mp4" >&2
  exit 1
fi
SALIDA="${VIDEO%.*}_revision.jpg"
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$VIDEO")
ffmpeg -v error -y -i "$VIDEO" \
  -vf "fps=2,scale=200:-1,drawtext=text='%{pts\:hms}':x=4:y=4:fontsize=13:fontcolor=white:box=1:boxcolor=black@0.6,tile=10x7" \
  -frames:v 1 "$SALIDA" 2>/dev/null \
|| ffmpeg -v error -y -i "$VIDEO" -vf "fps=2,scale=200:-1,tile=10x7" -frames:v 1 "$SALIDA"

# Tramos casi quietos: si en 3 s seguidos la imagen no cambia, la regla de ritmo se rompió.
QUIETOS=$(ffmpeg -i "$VIDEO" -vf "freezedetect=n=0.002:d=3" -map 0:v -f null - 2>&1 | grep -c "freeze_start" || true)
echo "Duración: ${DUR}s · tramos quietos de 3 s o más: ${QUIETOS}"
echo "Hoja de revisión: $SALIDA"
