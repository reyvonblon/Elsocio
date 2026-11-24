# ESTADO
## Base aprobada
- Motor y orquestador autónomo: `socio_cerebro.py` unifica en orden real: IMAP + landing (`telefono`+`correo`+`mensaje`) → `prospect_hunter.py` (MX OK) → `sales_agent.py` → SMTP (`autopilot_dispatcher.py`) → `content_brain.py` → `ig_publisher.py` → silencios/métricas reales + panel `8787`.
- Nichos activos: `modelado-3d-espacios`, `fichas-tecnicas-ropa`. `sales_agent.py` carga skills de calidad y el dolor/ángulo de `nichos/*.md` recortando en código `Precio de referencia` y cualquier cifra.
- Landing `docs/index.html` → WhatsApp + Web3Forms → `sync_landing_messages()` → notifica Mac + Calendar.app + activa `sales_agent` si dejaron correo. Gmail `elsociotuia@gmail.com` activo.
- **Agente de ventas 6/6**: `sales_agent.py` (stdlib, Sonnet 5, topes 15 correos y `0.50 USD/día`, 6 turnos, 2 reintentos, prompt caching `ephemeral`). Alcance: cliente calificado + aviso a Raymond; precio y link de pago solo los pone Raymond (`MODO_TRABAJO.md`).
- Guardas en CÓDIGO: precios, monedas, porcentajes, cifras pegadas/separadas, métodos de pago y links con hostname exacto; baja procesada antes de cualquier tope y sin falsos positivos; lead cerrado o `bounced=1` nunca recibe correo; frío nunca se repite.
- `registrar_resultado_mercado()` en `RESULTADOS_MERCADO.md`: solo eventos reales (respuesta, baja, rebote permanente SMTP, silencio a 7 días y comentarios reales de IG), sanitizando celdas sin borrar historial.
- **Contenido 3/3 + Voz Humana**: `content_queue` + `content_manager.py` + `ReelVertical` 1080x1920@30fps con 4 escenas SVG isométricas (`EscenasIsometricas.tsx`). `voice_engine.py` (stdlib) genera locución neuronal cálida en una sola toma continua (`en-US-AndrewMultilingualNeural` gratis por defecto, u OpenAI/ElevenLabs), sincroniza cada subtítulo vía `SentenceBoundary` y masteriza a `-14 LUFS` en `generar_video.sh`.
- `content_brain.py` piensa ganchos/guiones sin repetir, leyendo dolores reales y compartiendo el mismo tope de `0.50 USD/día` (vender va primero que publicar).
- **Instagram Oficial + Panel 8787**: `ig_publisher.py` publica solo por Meta Graph API (`IMAGE` con conversión `.png→.jpg` vía `sips` y `REELS` con polling `FINISHED`), autodescubre `IG_USER_ID` desde el token, auto-renueva tokens cada 25 días, respeta tope diario, interruptor `ig_auto_publish` y rollback limpio. `panel_server.py` sirve preview visual + conexión de claves + interruptor en WiFi `8787`; `instalar_piloto.py` configura `launchd`.
- **208 pruebas en seco en verde** (`128` ventas + `55` contenido + `25` cerebro autónomo); huellas SHA-256 de `data/el_socio.db` y `RESULTADOS_MERCADO.md` intactas.
## En prueba / Pendiente de encendido
- Faltan en `.env` para operar en vivo: `ANTHROPIC_API_KEY` (enciende cerebro de ventas y contenido) y `IG_USER_ID` + `IG_ACCESS_TOKEN` (enciende publicación automática en Instagram). Gmail SMTP/IMAP ya está listo.
## Descartado
- Voces robóticas de sistema (`say`): reemplazadas por voz neuronal humana sincronizada. Bots/scrapers no oficiales de IG: prohibidos por baneo (solo Meta Graph API).
- `remotion render` directo en Monterey (se usa `--sequence` PNG + `ffmpeg` con autodetección de dígitos). Tailscale en Monterey (solo WiFi local `8787`). Calendly externo. Contestar ruido (`respuesta_recibida`) con saldo de IA o registrar `silencio` el mismo día del envío.
