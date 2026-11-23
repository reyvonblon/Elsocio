# ESTADO

## Base aprobada
- Motor de prospección (prospect_hunter.py) + envío/respuestas (autopilot_dispatcher.py) + SQLite, adaptado del motor probado de Tu Parche En Vivo.
- 2 nichos de arranque: modelado-3d-espacios, fichas-tecnicas-ropa. Sistema abierto a cualquier nicho nuevo (`nuevo-nicho.md`).
- 5 skills de calidad (humanizer, pensamiento-critico, psicologia-y-estatus, inteligencia-competitiva, editor-implacable).
- Creación real de eventos en Calendar.app vía AppleScript cuando un lead responde interesado (probado, funciona).
- Landing `docs/index.html`: solo logo + caja de texto ("Escribe lo que necesitas..."). Al enviar: abre WhatsApp con el mensaje Y manda copia silenciosa por Web3Forms a elsociotuia@gmail.com. Repo: github.com/reyvonblon/Elsocio.git.
- Backend de la landing: `sync_landing_messages()` en `autopilot_dispatcher.py` lee esos correos por IMAP, los guarda en tabla `landing_messages` (SQLite), notifica en el Mac y crea evento en Calendar. Manejado 100% por El Socio, sin dashboards ni pasos manuales de Raymond.
- Gmail dedicado: elsociotuia@gmail.com.

## En prueba
- Falta contraseña de aplicación de Gmail en `.env` — SIN esto, `sync_landing_messages` no puede leer los mensajes de la landing (el correo llega pero nadie lo recoge).
- GitHub Pages activado (main → /docs): https://reyvonblon.github.io/Elsocio/
- Tarea diaria programada con launchd: `com.elsocio.landing` (revisa correo cada 10 min, notifica Mac + Calendar) y `com.elsocio.panelserver` (sirve el panel en la red local, puerto 8787) — ambas corriendo.

## Descartado
- Tailscale para ver el panel desde el celular fuera de casa: la versión actual ya no soporta macOS Monterey (error confirmado en log de instalación: kLSIncompatibleSystemVersionErr). Se queda con acceso solo por WiFi de casa (http://192.168.1.44:8787/mensajes.html) hasta encontrar alternativa compatible.
- Calendly / login externo para agendar: Raymond solo quiere el Calendario local de Mac.
- Clonar skills de repos externos de GitHub: alto riesgo de inventar contenido — se reescribieron a mano.
- "Cargar todas las skills sin límite" en CLAUDE.md: degrada calidad — se limitó a 3-4 relevantes por tarea.
