# ESTADO
## Base aprobada
- Orquestador `socio_cerebro.py` (launchd cada 15 min): IMAP+landing → `prospect_hunter` → `sales_agent` → SMTP → `content_brain` → `ig_publisher` → panel `8787`. Todo en `data/el_socio.db`.
- Nichos (Medellín/Bogotá/Cali/Barranquilla): modelado-3d, fichas-ropa, ecommerce-visual, automatización-agencias. Precio y link de pago: solo Raymond.
- Correo: 15/día máx, 1 cada 15-16 min, ventana 8-21 hora local. Guardas de precios/cifras en código.
- Reels: 3 formatos rotan (`ReelAuto.tsx`), voz Giuseppe Multilingual fija, -14 LUFS. Carrusel vía `CarruselLaminas.tsx`.
- IG: solo Meta Graph API, token auto-renovado. Cuenta real `@elsociotuia` id `17841438802416058`.
- 257 pruebas en verde.
## Lo que se arregló el 2026-11-25
- IG publicaba contra la cuenta vieja restringida: `.env` tenía el `IG_USER_ID` de `inmocolombia` y el código solo usaba el de la BD si `.env` estaba vacío. Corregido → 6 piezas reales publicadas hoy.
- Rebotes diferidos: llegan del `mailer-daemon`, no eran lead y se descartaban en silencio; `hola@hades.com` llevaba 2 días rechazando y seguía recibiendo. Ya se detectan y cortan.
- Correo sin ancho máximo (se estiraba en pantalla ancha) → 600px. `From` ahora lleva nombre. Logo con `EMAIL_LOGO=1`, apagado en frío (imagen de marca = pestaña Promociones).
- Basura filtrada: portales de empleo (`magnetoempleos.com`) y nombres de empresa que eran consultas de Google.
- Presupuesto: `CONTENT_MAX_DAILY_USD=0` y reserva ventas `0.50`. No se crea contenido con IA; publicar no gasta, así que el contenido sigue saliendo con lo ya pagado.
## En prueba / Pendiente
- Cola: 6 piezas generadas listas (sin el carrusel que sale hoy). Mañana el motor reparte 6 a lo largo del día.
- Sin respuestas de prospectos todavía: 26 correos enviados, 0 interesados. Falta la 1ª venta.
- Riesgo abierto: vaciar la cola de golpe en una cuenta de 1 seguidor es el patrón que ya hizo que Meta restringiera la cuenta anterior.
## Descartado
- Voces robóticas (`say`), bots/scrapers no oficiales de IG, `remotion render` directo en Monterey, Tailscale, Calendly externo, contestar ruido con saldo de IA.
- Falsas alarmas verificadas: no hay ráfaga de correos, ni envíos de madrugada, ni acentos rotos (eso era mi vista previa).
