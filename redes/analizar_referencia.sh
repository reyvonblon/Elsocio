#!/bin/bash
# Descompone un video de referencia para estudiarlo fotograma por fotograma.
#
# Uso:
#   ./analizar_referencia.sh "ruta/al/video.mov"                 # todo el video
#   ./analizar_referencia.sh "ruta/al/video.mov" 30 30           # solo del segundo 30 al 60
#
# Deja en contexto/referencias_video/analisis/<nombre>/:
#   general.jpg   hoja de contacto, 1 fotograma cada 3 s (para ubicar cada reel dentro de la grabación)
#   densa.jpg     hoja de contacto del tramo pedido a 2 fotogramas por segundo, con el segundo marcado
#   cortes.txt    segundos exactos donde cambia el plano (detección de escena de ffmpeg)
#   corte_*.jpg   el fotograma completo justo después de cada corte (para ver el detalle de cada toma)
#   ficha.txt     resolución, duración, fps y si tiene audio
#
# Después de correrlo: abrir las imágenes y llenar la tabla de storyboard de
# `contexto/director-de-video.md` (frase → qué se ve → cómo se mueve la cámara).

set -e
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"

VIDEO="$1"
INICIO="${2:-0}"
DURACION="${3:-}"
if [ -z "$VIDEO" ] || [ ! -f "$VIDEO" ]; then
  echo "Uso: ./analizar_referencia.sh \"video.mov\" [inicio_seg] [duracion_seg]" >&2
  exit 1
fi

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
NOMBRE="$(basename "$VIDEO" | sed 's/\.[^.]*$//' | tr ' ()' '___' | tr -cd 'A-Za-z0-9._-')"
SALIDA="$RAIZ/contexto/referencias_video/analisis/${NOMBRE}_${INICIO}"
mkdir -p "$SALIDA"
rm -f "$SALIDA"/corte_*.jpg

TRAMO=(-ss "$INICIO")
if [ -n "$DURACION" ]; then TRAMO+=(-t "$DURACION"); fi

# Ficha técnica
{
  echo "archivo: $VIDEO"
  ffprobe -v error -show_entries format=duration -of default=nw=1 "$VIDEO"
  ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate -of default=nw=1 "$VIDEO"
  if ffprobe -v error -select_streams a -show_entries stream=codec_type -of csv=p=0 "$VIDEO" | grep -q audio; then
    echo "audio: sí"
  else
    echo "audio: NO (las reglas de voz/música no se pueden medir con este archivo)"
  fi
} > "$SALIDA/ficha.txt"

# Hoja general: 1 fotograma cada 3 s
ffmpeg -v error -y -i "$VIDEO" -vf "fps=1/3,scale=160:-1,tile=10x8" -frames:v 1 "$SALIDA/general.jpg"

# Hoja densa del tramo: 2 fps con marca de tiempo
ffmpeg -v error -y "${TRAMO[@]}" -i "$VIDEO" \
  -vf "fps=2,scale=180:-1,drawtext=text='%{pts\:hms}':x=4:y=4:fontsize=13:fontcolor=white:box=1:boxcolor=black@0.6,tile=10x6" \
  -frames:v 1 "$SALIDA/densa.jpg" 2>/dev/null \
|| ffmpeg -v error -y "${TRAMO[@]}" -i "$VIDEO" -vf "fps=2,scale=180:-1,tile=10x6" -frames:v 1 "$SALIDA/densa.jpg"

# Cortes de plano. Se mide sobre el video completo recortado con `trim` para que los segundos
# sean absolutos, y se juntan los micro-cambios (texto entrando palabra por palabra) que caen a
# menos de 0.6 s del corte anterior: lo que queda son cambios de toma reales.
FIN_TRIM=""
if [ -n "$DURACION" ]; then FIN_TRIM=":duration=${DURACION}"; fi
ffmpeg -i "$VIDEO" -vf "trim=start=${INICIO}${FIN_TRIM},select='gt(scene,0.12)',showinfo" -f null - 2>&1 \
  | grep -o "pts_time:[0-9.]*" | cut -d: -f2 \
  | awk 'BEGIN { u = -10 } { if ($1 - u >= 0.6) { printf "%.2f\n", $1; u = $1 } }' > "$SALIDA/cortes.txt"

# Un fotograma completo después de cada corte (máx 40)
n=0
while read -r t; do
  n=$((n + 1))
  [ "$n" -gt 40 ] && break
  ffmpeg -v error -y -ss "$(awk -v t="$t" 'BEGIN { printf "%.2f", t + 0.25 }')" -i "$VIDEO" -frames:v 1 "$SALIDA/corte_$(printf '%02d' $n)_${t}s.jpg"
done < "$SALIDA/cortes.txt"

echo "Cortes detectados: $(wc -l < "$SALIDA/cortes.txt" | tr -d ' ')"
if [ "$(wc -l < "$SALIDA/cortes.txt")" -gt 1 ]; then
  awk 'NR>1 { d=$1-p; s+=d; c++ } { p=$1 } END { if (c) printf "Intervalo medio entre cortes: %.2f s\n", s/c }' "$SALIDA/cortes.txt"
fi
echo "Listo: $SALIDA"
