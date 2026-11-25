# ESTADO
## Base aprobada
- Orquestador `socio_cerebro.py` (launchd cada 15 min): IMAP+landing → `prospect_hunter` → `sales_agent` → SMTP → `content_brain` → `ig_publisher` → panel `8787`. Todo en `data/el_socio.db`.
- Nichos (Medellín/Bogotá/Cali/Barranquilla): modelado-3d, fichas-ropa, ecommerce-visual, automatización-agencias. Precio y link de pago: solo Raymond.
- Correo: 15/día máx, 1 cada 15-16 min, ventana 8-21 hora local. Guardas de precios/cifras en código.
- Reels: 3 formatos rotan (`ReelAuto.tsx`), voz Giuseppe Multilingual fija, -14 LUFS. Carrusel vía `CarruselLaminas.tsx`.
- IG: solo Meta Graph API, token auto-renovado. Cuenta real `@elsociotuia` id `17841438802416058`.
- Monitor móvil real `panel/monitor.html` (PWA, ícono de `El Socio.app`): pide `/api/estado` y `/api/preguntar` al mismo `panel_server.py:8787` (cero dato inventado; sin cotizado/vendido porque esa plata no se registra todavía). Botón pausar lead = real (`cancel_followups_for_lead` + flag en `settings`).
- Notificación push al celular en fallos reales (`scripts/notificar.py` + ntfy.sh, gratis): se activa solo si pones `NTFY_TOPIC` en `.env`; sin eso no hace nada. Dispara desde `database.log_agent_action` cuando la herramienta es de error o hay `bloqueado_por_guarda`.
- 262 pruebas en verde (incluye `test_sales_agent`, `test_autonomous_brain`, `test_content_manager`; se corren con `python3 scripts/test_X.py`, no hay pytest instalado).
## En prueba / Pendiente
- Cola de correo: 33 personas reales (2 días a 15/día). Buscador: ~28 personas por 104 consultas (~50 min, 0 USD) — el techo es que sitios colombianos solo publican `info@`.
- Sin respuestas de prospectos todavía: 0 interesados reales en `processed_replies` (solo rebotes SMTP). Falta la 1ª venta.
- Riesgo abierto: vaciar la cola de golpe en una cuenta de 1 seguidor es el patrón que restringió la cuenta IG anterior.
- Meta unificó `tuparcheenvivo` + `elsociotuiaa` + Facebook; usuario pasó a `elsociotuia`. Falta revisar si proyectos vecinos comparten correo/WhatsApp.
## Descartado
- Voces robóticas (`say`), bots/scrapers no oficiales de IG, `remotion render` directo en Monterey, Tailscale, Calendly externo, contestar ruido con saldo de IA.
- WhatsApp Business API para el monitor móvil: el motor real es por correo (SMTP/IMAP), no hay canal de chat en vivo todavía.
