# ESTADO

## Base aprobada
- Motor de prospección (prospect_hunter.py) + envío/respuestas (autopilot_dispatcher.py) + SQLite, adaptado del motor probado de Tu Parche En Vivo.
- 2 nichos de arranque: modelado-3d-espacios, fichas-tecnicas-ropa. Sistema abierto a cualquier nicho nuevo (`nuevo-nicho.md`).
- 5 skills de calidad (humanizer, pensamiento-critico, psicologia-y-estatus, inteligencia-competitiva, editor-implacable).
- Creación real de eventos en Calendar.app vía AppleScript cuando un lead responde interesado.

## En prueba
- Falta: cuenta Gmail dedicada creada por Raymond y llenar `.env`.
- Falta: programar la tarea diaria (cron/launchd) para que corra solo.
- Falta: probar el primer envío real y validar que no caiga en spam.

## Descartado
- Clonar skills de repos externos de GitHub (louisblythe/Sales-Skills, coreyhaines31/marketingskills, LeadMagic/gtm-skills): alto riesgo de inventar contenido si la estructura del repo cambia — se reescribieron a mano en su lugar.
- "Cargar todas las skills sin límite" en CLAUDE.md: degrada calidad por exceso de contexto — se limitó a 3-4 relevantes por tarea.
