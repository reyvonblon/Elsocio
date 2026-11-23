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

## Paso 3 — Retroalimentación con leads reales (pendiente)

- Cruzar lo que responden los leads (`agent_log`, respuestas clasificadas) con los ganchos publicados:
  qué dolor concreto hace que alguien conteste, y convertirlo en la frase del próximo post.
- Al revés también: la frase que más guarda/comenta la gente entra al banco de ganchos del outreach.
- **Comparte el mismo tope de 0.50 USD/día del agente de ventas.** No es un presupuesto aparte: si el día
  ya se gastó contestando leads, el contenido espera. Vender va primero que publicar.
