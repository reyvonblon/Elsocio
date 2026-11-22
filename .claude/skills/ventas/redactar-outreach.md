# Redactar outreach

Cuándo usar: cuando hay que escribir el primer mensaje de contacto (o un seguimiento) para un lead
descubierto por `scripts/prospect_hunter.py`, antes de meterlo en la cola de envío (`database.enqueue_email`).

## Pasos
1. Lee el archivo del nicho correspondiente en `nichos/` — usa el "Ángulo de venta" y el "Dolor real" de ahí,
   no inventes un ángulo distinto.
2. Identifica un detalle real y verificable del lead (nombre del negocio, algo visible en su web) para
   personalizar las primeras dos líneas. Si no hay dato real disponible, usa un gancho genérico del nicho
   pero nunca inventes un detalle falso sobre ese negocio específico.
3. Redacta: gancho con el dolor real → una línea de qué se ofrece → un llamado a la acción único y claro.
4. Pasa el borrador por `psicologia-y-estatus.md`, `humanizer.md` y `editor-implacable.md` antes de entregarlo.
5. Solo entonces se encola con `database.enqueue_email(recipient=..., subject=..., body=..., nicho=...)`.

## Longitud
Máximo 80 palabras para un primer contacto. Nadie lee un correo largo de alguien que no conoce.
