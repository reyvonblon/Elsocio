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
- DESBLOQUEADO Meta (2026-11-25): el fallo NO era permiso de Meta. `.env` tenia `IG_USER_ID` de la
  cuenta vieja restringida (`inmocolombia`) y `ig_publisher` solo usa el id de la BD cuando `.env` esta
  vacio, asi que publicaba contra la cuenta mala. Corregido a `17841438802416058` (`@elsociotuia`).
  Permisos reales: `instagram_content_publish` granted, cuota 100/dia. Primer post REAL publicado:
  https://www.instagram.com/p/DgLMj9YFpf4/ (pieza 4). Motor sigue solo: 1 pieza cada 75 min, 6/dia.
- Primer carrusel REAL: pieza 9 ya generada y en cola; sale sola hoy dentro del cupo.
- Saldo IA de hoy agotado (0.5017/0.50 USD): no se crean piezas nuevas hasta manana; las 11 ya
  generadas alcanzan para hoy y manana.
## Descartado
- Voces robóticas (`say`), bots/scrapers no oficiales de IG, `remotion render` directo en Monterey, Tailscale, Calendly externo, contestar ruido con saldo de IA.
