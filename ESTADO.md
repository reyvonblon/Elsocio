# ESTADO

## Base aprobada
- Motor de prospección (prospect_hunter.py) + envío/respuestas (autopilot_dispatcher.py) + SQLite, adaptado del motor probado de Tu Parche En Vivo.
- 2 nichos de arranque: modelado-3d-espacios, fichas-tecnicas-ropa. Sistema abierto a cualquier nicho nuevo (`nuevo-nicho.md`).
- 5 skills de calidad (humanizer, pensamiento-critico, psicologia-y-estatus, inteligencia-competitiva, editor-implacable).
- Creación real de eventos en Calendar.app vía AppleScript cuando un lead responde interesado (probado, funciona).
- Landing `docs/index.html`: solo logo + caja de texto ("Escribe lo que necesitas...") que abre WhatsApp con el mensaje listo. Backend = WhatsApp (sin servicios externos). Repo: github.com/reyvonblon/Elsocio.git.
- Gmail dedicado: elsociotuia@gmail.com.

## En prueba
- Falta contraseña de aplicación de Gmail en `.env`.
- Falta número real de WhatsApp en la landing.
- Falta programar la tarea diaria (cron/launchd) para que corra solo.
- GitHub Pages activado (main → /docs): https://reyvonblon.github.io/Elsocio/

## Descartado
- Calendly / login externo para agendar: Raymond solo quiere el Calendario local de Mac.
- Clonar skills de repos externos de GitHub: alto riesgo de inventar contenido — se reescribieron a mano.
- "Cargar todas las skills sin límite" en CLAUDE.md: degrada calidad — se limitó a 3-4 relevantes por tarea.
