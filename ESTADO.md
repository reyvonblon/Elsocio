# ESTADO
## Base aprobada
- Motor: `prospect_hunter.py` (descubre + verifica MX) + `autopilot_dispatcher.py` (SMTP/IMAP, límite, horario, pausas) + SQLite en `data/el_socio.db`. launchd: `com.elsocio.landing` (10 min) y `com.elsocio.panelserver` (8787).
- 2 nichos de arranque: modelado-3d-espacios, fichas-tecnicas-ropa. Nichos nuevos por `nuevo-nicho.md`. 5 skills de calidad obligatorias antes de entregar texto de venta.
- Landing `docs/index.html` → WhatsApp + Web3Forms → `sync_landing_messages()` → tabla `landing_messages` → notifica Mac + evento real en Calendar.app (AppleScript, probado). Repo github.com/reyvonblon/Elsocio.git, Pages en https://reyvonblon.github.io/Elsocio/
- Gmail dedicado elsociotuia@gmail.com. Canal IG (`redes/`): frases + fotos vía `generar_post.sh`; publicar sigue manual. Alcance del agente: cliente calificado + aviso al dueño; precio y link de pago solo los pone Raymond (`MODO_TRABAJO.md` manda sobre `identidad.md`).
- **Agente de ventas completo 6/6**: `sales_agent.py` (tool use, solo stdlib, Sonnet 5, topes 15 correos y 0.50 USD/día) enganchado al dispatcher (`--run-agent`). Guardas en CÓDIGO: precios, links con hostname exacto, cifras pegadas/separadas/porcentajes; la baja va antes de cualquier tope; lead cerrado o rebotado nunca recibe correo.
- Contactado en frío una vez = nunca vuelve a salir en frío (pasa a `contactado` al encolar). Seguimiento que falla queda `pendiente`, no `hecho`, y llega al modelo como seguimiento, no como primer contacto. Solo `interesado_cita` gasta saldo; "cuánto cuesta / precio / cuéntame / ejemplos / necesito" ya cuentan como interesado.
- **Paso 6**: `registrar_resultado_mercado()` agrega filas reales al final de `RESULTADOS_MERCADO.md` (valida canal/resultado, sanitiza `|` y saltos, nunca borra filas). Solo eventos reales: respuesta, baja, rebote permanente de SMTP (que además marca `bounced`) y silencio de tanda a los 7 días con conteo real, sin duplicar.
- Batería `scripts/test_sales_agent.py`: 128 pruebas en verde. Cada prueba corre contra BD y `RESULTADOS_MERCADO.md` temporales y verifica al terminar que no tocó los reales.
- Dato real de mercado hasta hoy: restaurantes por correo y WhatsApp de negocio = silencio total.
- **Contenido Paso 1/3**: `.gitignore` blindado contra multimedia pesada (.mov/.mp4/posts/voz/out). Los 3 videos de referencia medidos con ffprobe + 20 fotogramas → `contexto/guia-estilo-video.md` (corte cada ~2s, gancho en 0-2s, A vs B, 1 palabra resaltada) y `contexto/plan-contenido.md`. Pasos 2 y 3 pendientes.
## En prueba
- `--dry-run` seco en los 3 frentes: `sales_agent.py --dry-run`, `autopilot_dispatcher.py --dry-run` (solo resumen: ni cola, ni SMTP, ni landing, ni BD) y `--run-agent --dry-run`. Verificado: huella de `data/el_socio.db` y de `RESULTADOS_MERCADO.md` idéntica antes y después.
- Faltan en `.env`: contraseña de aplicación de Gmail (sin ella nadie recoge los mensajes de la landing) y `ANTHROPIC_API_KEY` (sin ella el agente solo corre en dry-run; saldo previsto 3 USD).
## Descartado
- `remotion render` directo: exige macOS 15. Funciona con frames PNG + ffmpeg, pero `element-%03d.png` topa a 999 frames (33s a 30fps): pasar a `%04d` en el Paso 2. Copiar el tratamiento de audio de las referencias: los 3 .mov no tienen pista de audio, solo se copia ritmo visual y estructura.
- Tailscale para el panel fuera de casa: no soporta Monterey. Solo WiFi de casa (http://192.168.1.44:8787/mensajes.html).
- Calendly o cualquier login externo para agendar: Raymond solo quiere el Calendario local del Mac. Clonar skills de repos de GitHub: riesgo de inventar — reescritas a mano. Cargar todas las skills: degrada calidad, máx 3-4 por tarea.
- Registrar una tanda como `silencio` el día del envío (dato falso: nadie tuvo tiempo de contestar; va con plazo de 7 días) y dejar que `respuesta_recibida` dispare el agente (con 3 USD, contestar "ok recibido" con el modelo es tirar el dinero).
