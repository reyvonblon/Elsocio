# ESTADO
## Base aprobada
- Orquestador `socio_cerebro.py` (launchd cada 15 min): IMAP+landing → `prospect_hunter` → `sales_agent` → SMTP → `content_brain` → `ig_publisher` → panel `8787`. Todo en `data/el_socio.db`.
- Nichos (Medellín/Bogotá/Cali/Barranquilla): modelado-3d, fichas-ropa, ecommerce-visual, automatización-agencias. Precio y link de pago: solo Raymond.
- Correo: 15/día máx, 1 cada 15-16 min, ventana 8-21 hora local. Guardas de precios/cifras en código.
- Reels: 3 formatos rotan (`ReelAuto.tsx`), voz Giuseppe Multilingual fija, -14 LUFS. Carrusel vía `CarruselLaminas.tsx`.
- Subtítulo karaoke en los 3 formatos (2026-11-26): la caja vino viaja palabra por palabra con la voz (`tiemposPalabras`, `comun.tsx`); collage ya muestra la frase completa. Para iterar sin render: `npx remotion still` funciona en Monterey con `--browser-executable` del Chrome del sistema (~25 s).
- IG **BLOQUEADO** (2026-11-26): Meta responde `API access blocked`. La app `El Socio` (29395114573473845) rechaza al usuario `122093941137570741` (= elsociotuia@gmail.com, dueño del token guardado) con `Cannot call API for app on behalf of user` = app en modo desarrollo sin ese usuario en sus roles. El token del `.env` es de otra cuenta (Rey Vonblon) y solo autoriza `@inmocolombia`. Nada se publica hasta que Raymond arregle el acceso en Meta. `ig_publisher.verificar_acceso_ig()` ya lo detecta y lo dice.
- Monitor móvil real `panel/monitor.html` (PWA, ícono de `El Socio.app`): pide `/api/estado` y `/api/preguntar` al mismo `panel_server.py:8787` (cero dato inventado; sin cotizado/vendido porque esa plata no se registra todavía). Botón pausar lead = real (`cancel_followups_for_lead` + flag en `settings`).
- Notificación push al celular en fallos reales (`scripts/notificar.py` + ntfy.sh, gratis): se activa solo si pones `NTFY_TOPIC` en `.env`; sin eso no hace nada. Dispara desde `database.log_agent_action` cuando la herramienta es de error o hay `bloqueado_por_guarda`.
- 262 pruebas en verde (incluye `test_sales_agent`, `test_autonomous_brain`, `test_content_manager`; se corren con `python3 scripts/test_X.py`, no hay pytest instalado).
## En prueba / Pendiente
- Cola: **40 personas** (2.5 días). Rendimiento medido hoy por fuente, todas a 0 USD: buscadores 28 personas/120 consultas (~50 min) · rescate de descartados 5/95 dominios (~40 min) · OpenStreetMap **0**/48 dominios (~35 min).
- Cuello de botella real: no es encontrar empresas, es que la PyME colombiana no publica a su gente en la web. Ninguna fuente basada en sitios lo resuelve. Sin medir: si a `info@` con mensaje para reenviar al dueño responde más que no escribirle (los 26 viejos eran buzones CON mensaje genérico: no prueban nada).
- Sin respuestas de prospectos todavía: 0 interesados reales en `processed_replies` (solo rebotes SMTP). Falta la 1ª venta.
- Riesgo abierto: vaciar la cola de golpe en una cuenta de 1 seguidor es el patrón que restringió la cuenta IG anterior.
- Meta unificó `tuparcheenvivo` + `elsociotuiaa` + Facebook; usuario pasó a `elsociotuia`. Falta revisar si proyectos vecinos comparten correo/WhatsApp.
## Descartado
- Voces robóticas (`say`), bots/scrapers no oficiales de IG, `remotion render` directo en Monterey, Tailscale, Calendly externo, contestar ruido con saldo de IA.
- WhatsApp Business API para el monitor móvil: el motor real es por correo (SMTP/IMAP), no hay canal de chat en vivo todavía.
