# Plan de `scripts/sales_agent.py` (contexto vivo — leer antes de tocar el agente)

Agente de ventas con tool use. Solo stdlib (`urllib.request` → `https://api.anthropic.com/v1/messages`).
Cero SDKs, cero dependencias. Mac Intel / Monterey.

## Variables de entorno (en `.env`, nunca en el código, nunca impresas)
- `ANTHROPIC_API_KEY` — si falta, el agente sale limpio sin llamar a la API.
- `SALES_AGENT_MODEL` — default `claude-sonnet-5`.
- `SALES_AGENT_MAX_EMAILS` — default `15` (correos encolados por el agente al día).
- `SALES_AGENT_MAX_DAILY_USD` — default `0.50` (saldo total previsto: 3 USD).

## System prompt
Se lee en tiempo de ejecución de `contexto/identidad.md` (nunca copiado al código).
Nunca lee `contexto/precios-del-dueño.md`. Prompt Caching activo:
`system=[{"type":"text","text":prompt,"cache_control":{"type":"ephemeral"}}]`.

## Las 5 herramientas
1. `enviar_correo` — encola en `outbox` vía `database.enqueue_email` (nunca SMTP directo).
2. `programar_seguimiento` — `database.schedule_followup` (máximo 2 por lead).
3. `cambiar_etapa` — mueve la etapa del lead; si es `no_interesado`/`baja` cancela todo lo pendiente.
4. `avisar_al_dueño` — notificación en el Mac + nota en el lead.
5. `pedir_precio_al_dueño` — etapa `esperando_precio_dueño` + notificación + evento en Calendar.

## Guardas obligatorias (en CÓDIGO, no solo en el prompt)
- Antes de llamar a la API: sin API key → salir; `agent_emails_queued_today() >= SALES_AGENT_MAX_EMAILS` → salir;
  `agent_cost_today_usd() >= SALES_AGENT_MAX_DAILY_USD` → salir.
- `MAX_TURNS = 6` cortado en Python. Máximo 2 reintentos ante 429/5xx. Nunca loop infinito.
- Guarda de precios en `enviar_correo`: bloquea `$`, `COP`, pesos/usd/dólares, precio/vale/cuesta/tarifa/cobro/anticipo,
  cifras con mil/millón, cifras en letras ("veinticinco mil") y links o métodos de pago
  (nequi, daviplata, wompi, mercadopago, payu, stripe, paypal, pse, bancolombia, links externos).
  Si dispara: fila en `agent_log` con `bloqueado_por_guarda`, error al modelo, NO encola, NO gasta cupo.
- Correo en frío sin línea de baja: se le agrega automáticamente en código antes de encolar.
- `already_emailed_today(recipient)` → no duplica.
- `--dry-run`: no escribe en BD, no encola y NO llama a la API (no gasta saldo). Para probar contra
  Anthropic en seco hay que pedirlo con `--dry-run --con-api`, y aun así revisa los topes de correos
  y de USD antes y dentro del loop.
- Lead en `baja` / `no_interesado` o `bounced=1`: se corta en `correr()` antes de la API y otra vez
  dentro de `enviar_correo`. Nunca se le escribe.
- Si el mensaje del lead pide la baja, el CÓDIGO le pone etapa `baja` y cancela outbox +
  seguimientos. No se depende de que el modelo llame `cambiar_etapa`. Las frases explícitas
  ("no me escriban", "darme de baja", "unsubscribe", "esto es spam") valen en cualquier parte;
  las palabras sueltas `baja` y `stop` SOLO si son el mensaje entero ("BAJA", "baja por favor"),
  para no leer una baja en "foto de baja resolución", "planta baja" o "video stop motion".
- La baja se procesa ANTES de los topes diarios y de exigir la API key: cuesta 0 USD y 0 correos.
  Nunca crea el lead si no existe, y en `--dry-run` no toca la BD.
- Links: se parsea el hostname con `urllib.parse.urlparse` y se compara EXACTO contra la lista blanca.
  Así caen `pagos.evil.com/?r=reyvonblon.github.io` y `reyvonblon.github.io.evil.com`. También caen
  acortadores y links sin esquema (`mpago.la/x`, `bit.ly/x`, `wa.link/x`, `checkout.*`).
- Cifras: además de lo anterior, bloquea enteros pegados de 5+ dígitos (`25000`, `50000`), espacio
  como separador de miles (`50 000`) y porcentajes (`50%`, `20 por ciento`, prohibidos por
  `identidad.md`). También `transferencia`/`transferir`, `bre-b` y `cobra`/`cobre`/`cobrando`.
- De los links propios se borra solo el esquema + host + dígitos del path (`wa.me/573001112233`);
  la query se CONSERVA y se vuelve legible, así que `wa.me/573001112233?text=pagar_50000_nequi`
  se bloquea. Un link con query sin barra (`evil.com?a=1`) también cuenta como link.
- 429/5xx: pausa de `1.5 * (intento + 1)` segundos antes de cada reintento (máximo 2).

## Checklist de los 6 pasos
1. [hecho] Contexto y alcance (`MODO_TRABAJO.md`, este archivo).
2. [hecho] DB: tablas `agent_log` / `agent_followups` + topes + costo en USD.
3. [hecho] Núcleo de `sales_agent.py` (loop, herramientas, guardas).
4. [hecho] Pruebas exhaustivas en seco: `scripts/test_sales_agent.py` (`unittest` de
   stdlib, BD temporal en /tmp, cero red). Cubre: `--dry-run` no toca `data/el_socio.db` ni llama a la
   API, guarda de precios y links (bloqueados y legítimos), línea de baja automática, duplicados del
   mismo día con mayúsculas, cancelación al dar de baja, leads cerrados/rebotados, topes de 15 correos
   y 0.50 USD verificados antes de la API, corte duro en 6 turnos y 2 reintentos con pausa ante 429.
   Se corre con `python3 scripts/test_sales_agent.py`. Hoy son 68 pruebas en verde.
5. [hecho] Enganche en `autopilot_dispatcher.py`:
   - `classify_reply_intent()` devuelve `baja` cuando el cuerpo limpio dispara `pide_la_baja()`
     (después del filtro de autorespondedores: un pie con "unsubscribe" no es una baja).
   - `sync_imap_replies()` cancela outbox Y `agent_followups` ante CUALQUIER respuesta, y corre
     el agente solo si el intent es `interesado_cita` o `respuesta_recibida` y hay API key, dentro
     de un `try/except` para que nunca rompa el sync, el aviso del Mac ni el evento de Calendar.
   - `run_sales_agent_cycle(dry_run=, max_leads=)`: sin API key sale limpio; respeta la ventana
     horaria; 1º seguimientos vencidos (`cancelado` sin gastar un token si el lead está cerrado o
     rebotado, `hecho` si corrió), 2º leads nuevos en frío; corta de inmediato ante 15 correos o
     0.50 USD. En `--dry-run` no escribe nada y no crea la BD.
   - Doble seguro en `dispatch_due_jobs()`: un job cuyo lead pasó a `baja`/`no_interesado` o
     rebotó se marca `cancelled` y NO se envía, aunque ya estuviera en la cola.
   - Flags nuevos: `--run-agent` y `--dry-run`. El `main()` normal corre el ciclo solo si hay
     `ANTHROPIC_API_KEY`, y si falta no rompe nada.
6. [pendiente] Escritura automática en `contexto/RESULTADOS_MERCADO.md`.
