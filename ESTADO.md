# ESTADO
## Base aprobada
- Motor: `prospect_hunter.py` (descubre + verifica MX) + `autopilot_dispatcher.py` (SMTP/IMAP, límite, horario, pausas) + SQLite en `data/el_socio.db`.
- 2 nichos de arranque: modelado-3d-espacios, fichas-tecnicas-ropa. Abierto a nichos nuevos (`nuevo-nicho.md`).
- 5 skills de calidad (humanizer, pensamiento-critico, psicologia-y-estatus, inteligencia-competitiva, editor-implacable).
- Evento real en Calendar.app vía AppleScript cuando un lead responde interesado (probado).
- Landing `docs/index.html` (logo + caja de texto → WhatsApp + copia por Web3Forms) y su backend `sync_landing_messages()` → tabla `landing_messages` → notifica Mac + Calendar. Repo: github.com/reyvonblon/Elsocio.git, Pages en https://reyvonblon.github.io/Elsocio/
- Gmail dedicado elsociotuia@gmail.com. Canal IG (`redes/`): frases + fotos vía `generar_post.sh`; publicar sigue manual.
- launchd corriendo: `com.elsocio.landing` (cada 10 min) y `com.elsocio.panelserver` (puerto 8787).
- Alcance del agente fijado: cliente calificado + aviso al dueño. Precio y link de pago solo los pone el dueño (`MODO_TRABAJO.md` manda sobre `identidad.md`).
- `RESULTADOS_MERCADO.md` con columnas Canal y Cantidad. Primer dato real: restaurantes por correo y WhatsApp de negocio = silencio total.
## En prueba
- `sales_agent.py` (agente de ventas con tool use, solo stdlib, Sonnet 5 por `.env`, tope 5 correos/día): pasos 1-2 de 6 hechos (contexto + tablas `agent_log`/`agent_followups` probadas sin perder datos). Faltan núcleo, dry-run, enganche y escritura en RESULTADOS_MERCADO.
- Faltan en `.env`: contraseña de aplicación de Gmail (sin ella nadie recoge los mensajes de la landing) y `ANTHROPIC_API_KEY` (sin ella el agente solo corre en dry-run; saldo previsto 3 USD).
## Descartado
- `remotion render` directo: exige macOS 15. Funciona vía frames PNG + ffmpeg, pero el video está en pausa hasta validar que las fotos conviertan.
- Tailscale para el panel fuera de casa: no soporta Monterey. Solo WiFi de casa (http://192.168.1.44:8787/mensajes.html).
- Calendly o cualquier login externo para agendar: Raymond solo quiere el Calendario local del Mac.
- Clonar skills de repos externos de GitHub: alto riesgo de inventar contenido — se reescribieron a mano.
- "Cargar todas las skills sin límite": degrada calidad — limitado a 3-4 relevantes por tarea.
