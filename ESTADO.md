# ESTADO
## Base aprobada
- Orquestador `socio_cerebro.py` (launchd cada 15 min): IMAP+landing → `prospect_hunter` → `sales_agent` → SMTP → `content_brain` → `ig_publisher` → panel `8787`. Todo en `data/el_socio.db`.
- Nichos (Medellín/Bogotá/Cali/Barranquilla): modelado-3d, fichas-ropa, ecommerce-visual, automatización-agencias. Precio y link de pago: solo Raymond.
- Correo: 15/día máx, 1 cada 15-16 min, ventana 8-21 hora local. Guardas de precios/cifras en código.
- Reels: 3 formatos rotan (`ReelAuto.tsx`), voz Giuseppe Multilingual fija, -14 LUFS. Carrusel vía `CarruselLaminas.tsx`.
- IG: solo Meta Graph API, token auto-renovado. Cuenta real `@elsociotuia` id `17841438802416058`.
- 262 pruebas en verde.
## Lo que se arregló el 2026-11-25 (resumen)
- IG publicaba contra la cuenta vieja restringida (`IG_USER_ID` de `inmocolombia` en `.env`). Corregido.
- Rebotes diferidos del `mailer-daemon` ya se detectan y cortan. Correo a 600px y `From` con nombre.
- El buscador premiaba los buzones genéricos: invertido a persona +60/+35, buzón +10.
- Presupuesto repartido (ventas 0.41 / contenido 0.09, colchón 6 piezas). IG a 3 piezas/día.

## Lo que se arregló el 2026-11-26 (prospectos)
- `prospect_hunter.py` corrido a mano NO guardaba nada: imprimía 45 prospectos reales y los tiraba. Nuevo `--guardar`.
- Filtro duro: si un sitio no publica a una persona, se descarta el sitio. Antes el buzón de empresa se aceptaba "de últimas" y por eso seguían entrando `info@`, `hola@`, `ventas@`.
- Bug que botaba gente real: un correo que termina en números (`camilacarmona27@`) se partía con un espacio al final y fallaba `.isalpha()`.
- Escapes JSON del HTML: entraba `u003einfo@megapredios.com.co` como si fuera persona.
- Saludo más seguro: si el nombre es dudoso (`fpedraza`, `luisalfesp` = Luis o Luisa) saluda a la empresa, no inventa.
- Marcas que pasaban como persona: `cafealtoperfil`, `acuattro`, `taro`, `ccialviva`, `weare.cuero`, `papeleria.pdepapel`. Ahora fuera.
- Consultas de búsqueda ampliadas de 48 a 104 (Bucaramanga, Pereira, Cartagena, Manizales + verticales nuevos: ropa infantil/deportiva, cocinas, stands, fotografía de producto, eventos, mascotas).
- El reponedor solo buscaba para el día: la cola amanecía en cero y el buscador tarda ~30 min. Ahora apunta a un colchón (`autopilot_buffer_leads=45`).
- Cola: **33 personas reales** (antes 10). 17 buzones/marcas descartados sin contactar. 262 pruebas en verde.

## En prueba / Pendiente
- Cola de correo: 33 personas (2 días a 15/día). Rendimiento real del buscador: ~28 personas por 104 consultas (~50 min, 0 USD). Los sitios colombianos publican `info@`, no gente: ese es el techo.
- Sin respuestas de prospectos todavía: 26 correos enviados, 0 interesados. Falta la 1ª venta.
- Riesgo abierto: vaciar la cola de golpe en una cuenta de 1 seguidor es el patrón que ya hizo que Meta restringiera la cuenta anterior.
- Las 6 piezas del 25-nov SÍ se publicaron (`quota_usage: 5` en Meta); Raymond las archivó a mano, por eso `/media` sale vacío. Ojo: archivar deja el contenido invisible y sin métricas para `sincronizar_resultados_ig`.
- Meta unificó el 25-nov `tuparcheenvivo` + `elsociotuiaa` + Facebook en una cuenta, y el usuario pasó de `elsociotuiaa` a `elsociotuia`. Falta revisar si los proyectos vecinos comparten correo/WhatsApp/cuentas con El Socio.
## Descartado
- Voces robóticas (`say`), bots/scrapers no oficiales de IG, `remotion render` directo en Monterey, Tailscale, Calendly externo, contestar ruido con saldo de IA.
- Falsas alarmas verificadas: no hay ráfaga de correos, ni envíos de madrugada, ni acentos rotos (eso era mi vista previa).
