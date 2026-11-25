# ESTADO
## Base aprobada
- Orquestador: `socio_cerebro.py` encadena IMAP+landing → `prospect_hunter` → `sales_agent` → `autopilot_dispatcher` (SMTP) → `content_brain` → `ig_publisher` → panel `8787`.
- Nichos (Medellín/Bogotá/Cali/Barranquilla): `modelado-3d-espacios`, `fichas-tecnicas-ropa`, `ecommerce-catalogo-visual`, `automatizacion-agencias-estudios`. Precio y link de pago: solo Raymond.
- `sales_agent.py`: Sonnet 5 effort medium, flujo 6/6, tope 15 correos + `0.50 USD/día` compartido con contenido, prompt caching, guardas de precios/pago/cifras en código.
- Reels: 3 formatos rotan (`mundo`/`collage`/`duelo`, `ReelAuto.tsx`), storyboard por `planos`, cierre de venta fijo en código. Voz principal: Giuseppe Multilingual (`redes/voz/voz_definitiva_socio.m4a`, ya fija en `.env`) vía `voice_engine.py`, -14 LUFS.
- Contenido: `content_queue` + `content_manager.py` + `content_brain.py` planean mix diario (2 video + 1 post + 2 historia + 1 carrusel) en 1 llamada `ephemeral`, reservando presupuesto para ventas.
- Carrusel (tipo nuevo): `CarruselLaminas.tsx` + `generar_carrusel.sh` → `redes/carruseles/content_NNNN_01..XX.png`; `ig_publisher` lo sube como `CAROUSEL` oficial con láminas hijas. Render probado manualmente hoy: OK.
- IG: `ig_publisher.py` solo Meta Graph API (`IMAGE`/`REELS`/`STORIES`/`CAROUSEL`), auto-renueva token; `panel_server.py` sirve preview en `8787`.
- 257 pruebas en seco en verde; huellas SHA-256 de la BD y `RESULTADOS_MERCADO.md` intactas en dry-run.
- `generar_video.sh` tiene lock de carpeta (`out/.render.lock`, con detección de lock huérfano):
  dos renders a la vez ya no pueden chocar en `out/frames` y arruinarse mutuamente (2026-11-25).
- Motor (`com.elsocio.cerebro`, launchd cada 15 min) confirmado activo y corriendo solo.
## En prueba / Pendiente
- Meta DESBLOQUEADO (2026-11-25): el bloqueo era `IG_USER_ID` viejo en `.env` (cuenta restringida),
  no permisos. Ahora `17841438802416058` (`@elsociotuia`), `instagram_content_publish` OK, 100/dia.
- Publicado REAL: post https://www.instagram.com/p/DgLMj9YFpf4/ y primer REEL
  https://www.instagram.com/reel/DgLOh_ziseu/ (pieza 1 forzada a mano: el video nunca fue el problema).
- Hoy 2/6. Faltan 4 (video 2, historias 3 y 6, carrusel 9): salen solas cada 75 min, sin gastar IA.
  No forzarlas de golpe (rafaga = menos alcance).
- Presupuesto (2026-11-25): TODO el saldo a vender hasta la 1a venta. `CONTENT_MAX_DAILY_USD=0`
  y `CONTENT_SALES_RESERVE_USD=0.50`: el cerebro no crea piezas nuevas con IA, pero el publicador
  sigue subiendo las ya pagadas (publicar NO gasta IA). Ayer el contenido se comio el saldo y
  solo salieron 11 de 15 correos.
- Entregabilidad corregida (2026-11-25): rebotes diferidos del mailer-daemon ya se detectan y marcan
  el lead (antes se descartaban por no ser leads y se les seguia escribiendo: `hola@hades.com` llevaba
  2 dias rebotando). Correo acotado a 600px (se estiraba en pantalla ancha), `From` con nombre real,
  logo opcional por `EMAIL_LOGO=1` (apagado en frio: imagen de marca = pestana Promociones).
  Bloqueados portales de empleo (se gasto un correo en `magnetoempleos.com`) y nombres de empresa
  que eran consultas de Google ("Tienda naturista cerca de mi en Colombia por ciudad").
- Verificado y DESCARTADO como problema: no hay rafaga de correos (salen 1 cada 15-16 min) ni envios
  de madrugada (8:12-13:29 hora Colombia) ni acentos rotos (UTF-8 correcto en los correos reales).
- Panel 8787 publica directo sin la pausa de 75 min: es a proposito, Raymond lo usa para vaciar cola.
## Descartado
- Voces robóticas (`say`), bots/scrapers no oficiales de IG, `remotion render` directo en Monterey, Tailscale, Calendly externo, contestar ruido con saldo de IA.
