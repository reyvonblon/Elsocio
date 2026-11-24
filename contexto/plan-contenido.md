# Plan de contenido — unificar `redes/` con El Socio

Hoy `redes/` es un taller suelto: frases a mano, PNG generados con Chrome headless, un Remotion
que renderiza 1080x1350 y publicación 100% manual. No habla con el motor de ventas
(`sales_agent.py`, `autopilot_dispatcher.py`, `data/el_socio.db`). Estos 3 pasos lo conectan.

---

## Paso 1 — Guía destilada y Git blindado ✅ hecho

- `.gitignore` cerrado a multimedia pesada: `.mov`, `.mp4`, `redes/posts/*.png`, `redes/voz/*.aiff`,
  `redes/voz/*.m4a`, `redes/video-logo/out/`. Verificado con `git status`: nada pesado entra al repo.
- Los 3 videos de referencia medidos con `ffprobe`/`ffmpeg` (resolución, duración, fps, audio, cortes)
  y 20 fotogramas clave inspeccionados → `contexto/guia-estilo-video.md`.
- Hallazgo que condiciona todo lo demás: **las referencias no tienen pista de audio**. Lo que se puede
  copiar con certeza es el ritmo visual y la estructura de guion, no el tratamiento sonoro.
- `redes/ESTILO_VIDEO.md` borrado: la guía es la única fuente.

## Paso 2 — Que el contenido sea parte del motor ✅ hecho

1. **Tabla `content_queue`** en `data/el_socio.db` (`scripts/database.py`): una fila por pieza
   (tipo, nicho, gancho, guion, caption, estado, archivo, fechas). Se crea con `CREATE TABLE IF NOT
   EXISTS` junto al resto del esquema: no toca ni una fila de las tablas que ya estaban.
   Estados: `borrador → aprobado → generado → publicado`, más `descartado`.
2. **`scripts/content_manager.py`** (solo stdlib, cero llamadas a la API): encola, genera con
   `generar_post.sh` / `generar_video.sh`, marca `publicado` / `descartado`. **La guarda de precios
   corre en CÓDIGO** vía `sales_agent.revisar_guarda_precios()` sobre gancho + guion + caption, y se
   repite al generar (por si alguien editó la fila a mano en la BD). `--dry-run` no toca BD, no
   renderiza y no escribe en `RESULTADOS_MERCADO.md`.
3. **Plantilla Remotion vertical** `ReelVertical` 1080x1920 @ 30 fps, alineada a la guía: gancho desde
   el frame 1, un bloque cada 2 s, texto que se acumula, palabra final resaltada en vino, push-in lento
   y **texto en la mitad superior con una escena isométrica como único elemento héroe en la
   inferior** (`src/EscenasIsometricas.tsx`: `contraste`, `flujo`, `espacio3d`, `agenda`; se
   eligen con `--escena` y sus tooltips con `--etiquetas`). La duración se calcula con `calculateMetadata` según cuántos
   bloques trae el guion, así no quedan segundos muertos al final.
4. **`generar_video.sh`**: acepta `--reel` con props JSON y **detecta el relleno de ceros de los frames
   en tiempo de ejecución**. Remotion no siempre usa 4 dígitos (con pocos frames genera `element-0.png`),
   así que fijar `%04d` a mano habría roto el render: ahora el patrón sale del primer frame real.
5. **Panel** (`scripts/panel_mensajes.py`): segunda tabla con la cola de contenido. De paso se escapa con
   `html.escape()` todo lo que viene de fuera — el mensaje de la landing lo escribe un desconocido y sin
   eso un `<script>` suyo corría en el panel.
6. **`RESULTADOS_MERCADO.md`**: al publicar se llama a `registrar_resultado_mercado(..., canal="instagram")`
   con el resultado real que vio Raymond. Nada automático, nada inventado.
7. **Pruebas**: `scripts/test_content_manager.py`, 36 pruebas en seco (BD y archivo de resultados
   temporales, subprocess parcheado, cero red). Las 128 anteriores siguen en verde.

## Paso 3 — Cerebro autónomo, voz humana sincronizada e Instagram oficial ✅ hecho

- **`scripts/voice_engine.py`** (100% Python stdlib, cero `say` robótico): locución neuronal humana en español colombiano (`es-CO-GonzaloNeural` por WebSocket TLS + `Sec-MS-GEC` v2 gratis sin claves, o `OPENAI_API_KEY` / `ELEVENLABS_API_KEY` si se configuran). Limpia símbolos visuales (`·`, URLs), pasa cada frase por `revisar_guarda_precios()`, sincroniza `tiemposBloques` / `tiempoCierre` / `duracionFrames` en `ReelVertical.tsx` y masteriza la voz con `ffmpeg` a `-14 LUFS`.
- **`scripts/content_brain.py`**: lee identidad, guía de video, `FRASES.md`, skills de calidad, `nichos/*.md` (recortados sin precios en código), `RESULTADOS_MERCADO.md` y señales reales de clientes (landing + respuestas, sin PII), prohibiendo repetir ganchos previos. **Comparte el mismo tope diario de `0.50 USD` de `sales_agent.py`** en `agent_log` (vender siempre va primero que publicar).
- **`scripts/ig_publisher.py`**: publicación 100% por API oficial de Meta (`graph.instagram.com` / `graph.facebook.com`), conversión automática `.png → .jpg` con `/usr/bin/sips` (Meta rechaza PNG con error 2207005), subida HTTPS efímera de 1h, polling `status_code == FINISHED`, tope diario (`IG_MAX_DAILY_POSTS`), interruptor `ig_auto_publish` y rollback limpio si Meta falla.
- **`scripts/panel_server.py` + `scripts/socio_cerebro.py` + `scripts/instalar_piloto.py`**: panel interactivo en puerto `8787` con preview de imagen/`<video>` + interruptor Autónomo/Preview, y orquestador único para `launchd` cada 15 min.
- **Pruebas**: `scripts/test_autonomous_brain.py` (23 pruebas nuevas en seco; 206 pruebas totales en verde).
