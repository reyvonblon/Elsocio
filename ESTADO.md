# ESTADO
## Base aprobada
- Orquestador `socio_cerebro.py` (launchd cada 15 min): IMAP+landing → `prospect_hunter` → `sales_agent` → SMTP → `content_brain` → `ig_publisher` → panel `8787`. Todo en `data/el_socio.db`.
- Nichos (Medellín/Bogotá/Cali/Barranquilla): modelado-3d, fichas-ropa, ecommerce-visual, automatización-agencias. Precio y link de pago: solo Raymond.
- Correo: 15/día máx, 1 cada 15-16 min, ventana 8-21 hora local. Guardas de precios/cifras en código.
- Reels: 3 formatos rotan (`ReelAuto.tsx`), voz Giuseppe Multilingual fija, -14 LUFS. Carrusel vía `CarruselLaminas.tsx`.
- Subtítulo karaoke en los 3 formatos (2026-11-26): la caja vino viaja palabra por palabra con la voz (`tiemposPalabras`, `comun.tsx`); collage ya muestra la frase completa. Para iterar sin render: `npx remotion still` funciona en Monterey con `--browser-executable` del Chrome del sistema (~25 s).
- IG **DESBLOQUEADO** (2026-11-26): Raymond pegó token nuevo de `elsociotuia@gmail.com` (coincide con el `IG_USER_ID` ya configurado, @elsociotuia, Página "El Socio"). `verificar_acceso_ig()` confirma `puede_publicar: true` y la 1ª pieza real ya salió: reel #5 publicado de verdad, `https://www.instagram.com/reel/DgNrTq3Kgk8/`. Modo autónomo reactivado (`ig_auto_publish=1`). Hosting del archivo: `docs/ig-media/` (GitHub Pages propio) con `litterbox.catbox.moe` solo de respaldo si ese falla.
- Pendiente nuevo: contestar DMs/comentarios de Instagram no existe todavía. El token trae `instagram_manage_messages` (sirve para DMs) pero NO `instagram_manage_comments` (hace falta token nuevo con ese permiso si se quiere contestar comentarios).
- Monitor móvil real `panel/monitor.html` (PWA, ícono de `El Socio.app`): pide `/api/estado` y `/api/preguntar` al mismo `panel_server.py:8787` (cero dato inventado; sin cotizado/vendido porque esa plata no se registra todavía). Botón pausar lead = real (`cancel_followups_for_lead` + flag en `settings`).
- Notificación push al celular en fallos reales (`scripts/notificar.py` + ntfy.sh, gratis): se activa solo si pones `NTFY_TOPIC` en `.env`; sin eso no hace nada. Dispara desde `database.log_agent_action` cuando la herramienta es de error o hay `bloqueado_por_guarda`.
- 266 pruebas en verde (incluye `test_sales_agent`, `test_autonomous_brain`, `test_content_manager`; se corren con `python3 scripts/test_X.py`, no hay pytest instalado).
## En prueba / Pendiente
- Ciclo de insights disenado en `contexto/ciclo-insights.md`: solo los reels votan (historia = remarketing, no ensena), se optimiza guardado+compartido y NO vistas, 2 capturas por pieza (24h/7d), exploracion fija 20-25%. Ya implementado solo el paso 1: guarda `pide_interaccion` (la interaccion se merece, no se pide). Falta la tabla `content_metrics`, la captura por Graph API y el puntaje.
- Cola: **40 personas** (2.5 días). Rendimiento medido hoy por fuente, todas a 0 USD: buscadores 28 personas/120 consultas (~50 min) · rescate de descartados 5/95 dominios (~40 min) · OpenStreetMap **0**/48 dominios (~35 min).
- Cuello de botella real: no es encontrar empresas, es que la PyME colombiana no publica a su gente en la web. Ninguna fuente basada en sitios lo resuelve. Sin medir: si a `info@` con mensaje para reenviar al dueño responde más que no escribirle (los 26 viejos eran buzones CON mensaje genérico: no prueban nada).
- Sin respuestas de prospectos todavía: 0 interesados reales en `processed_replies` (solo rebotes SMTP). Falta la 1ª venta.
- Riesgo abierto: vaciar la cola de golpe en una cuenta de pocos seguidores es el patrón que restringió la cuenta IG anterior; por eso la cuota diaria quedó baja (2 video + 2 historia, 0 post/carrusel).
## Descartado
- Voces robóticas (`say`), bots/scrapers no oficiales de IG, `remotion render` directo en Monterey, Tailscale, Calendly externo, contestar ruido con saldo de IA.
- WhatsApp Business API para el monitor móvil: el motor real es por correo (SMTP/IMAP), no hay canal de chat en vivo todavía.
