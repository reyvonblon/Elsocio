#!/usr/bin/env python3
"""Cerebro autónomo de contenido de El Socio (Reels + Post + Historias). Solo Python stdlib.

Piensa y planifica el movimiento orgánico diario (por defecto: 2 Reels verticales
con voz humana + 1 Post + 2 Historias = 5 piezas/día), basándose en:
  - `contexto/identidad.md` + `contexto/MODO_TRABAJO.md`
  - `contexto/guia-estilo-video.md` + `redes/FRASES.md`
  - las skills de calidad (`humanizer`, `psicologia-y-estatus`, `editor-implacable`)
  - dolores reales de `nichos/*.md` (recortados sin precios en código)
  - aprendizaje real en `contexto/RESULTADOS_MERCADO.md`
  - dudas reales recibidas en `landing_messages` y `processed_replies` (sin PII)
  - ganchos ya usados en `content_queue` (prohibido repetir)

Reglas duras en código:
  1. Comparte el MISMO tope diario de USD (`SALES_AGENT_MAX_DAILY_USD`, 0.50 USD)
     que `sales_agent.py` en `agent_log`. Vender SIEMPRE va primero que publicar:
     protege una reserva exclusiva para ventas (`CONTENT_SALES_RESERVE_USD`) y un
     sub-tope propio de contenido (`CONTENT_MAX_DAILY_USD`).
  2. Cuota diaria configurable por tipo (`CONTENT_DAILY_VIDEOS=2`,
     `CONTENT_DAILY_POSTS=1`, `CONTENT_DAILY_STORIES=2`) y total (`CONTENT_MAX_DAILY_PIECES`).
     Cuando faltan varias piezas del día, genera el lote completo en UNA sola llamada
     con prompt caching `ephemeral` para cuidar al máximo cada centavo.
  3. Toda pieza pasa por `content_manager.revisar_pieza()` (`revisar_guarda_precios`)
     en código antes de entrar a la BD (máx. 2 turnos si requiere autocorrección).
  4. En `--dry-run` no gasta ni un token, no toca la BD y no renderiza.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import autopilot_dispatcher  # noqa: E402
import content_manager  # noqa: E402
import database  # noqa: E402
import sales_agent  # noqa: E402

GUIA_VIDEO_FILE = PROJECT_ROOT / "contexto" / "guia-estilo-video.md"
FRASES_FILE = PROJECT_ROOT / "redes" / "FRASES.md"
RESULTADOS_FILE = PROJECT_ROOT / "contexto" / "RESULTADOS_MERCADO.md"

MAX_TURNOS_CONTENIDO = 2
MAX_TOKENS_CONTENIDO = 1600
# 4400 era justo el largo de un mix completo con carrusel: el 2026-11-25 la respuesta se cortó
# en `stop=max_tokens` y se pagaron 0.1111 USD por un plan inservible (más el reintento). Un tope
# alto no cuesta más —solo se paga lo que el modelo escribe— y evita pagar por respuestas a medias.
MAX_TOKENS_PLAN_DIARIO = 8000
DIAS_SIN_REPETIR_TEMA_VIDEO = 20

DEFAULT_DAILY_VIDEOS = 2
DEFAULT_DAILY_POSTS = 1
DEFAULT_DAILY_STORIES = 2
DEFAULT_DAILY_CAROUSELS = 1

_PROPIEDADES_PIEZA = {
    "tipo": {
        "type": "string",
        "enum": ["video", "post", "historia", "carrusel"],
        "description": (
            "Formato de la pieza ('video' = Reel 1080x1920 de 18-28 s con voz humana y escena "
            "isométrica; 'post' = imagen 1080x1350 de frase contundente; 'historia' = vertical "
            "1080x1920 directa para Stories; 'carrusel' = varias láminas 1080x1350 que se deslizan: "
            "portada con el gancho, una idea por lámina y lámina de cierre)."
        ),
    },
    "nicho": {
        "type": "string",
        "description": "Nicho al que habla (ej. 'general', 'fichas-tecnicas-ropa', 'modelado-3d-espacios', 'ecommerce-catalogo-visual', 'automatizacion-agencias-estudios').",
    },
    "gancho": {
        "type": "string",
        "description": "Frase inicial de contraste o verdad incómoda (máx 12 palabras, cero cifras, presente desde el frame 1).",
    },
    "bloques": {
        "type": "array",
        "items": {"type": "string"},
        "description": (
            "Para 'video' (Reel): de 5 a 7 bloques cortos (4 a 9 palabras cada uno) armando un "
            "arco A vs B completo (dolor actual -> consecuencia -> giro -> primer paso -> ejecución "
            "-> cambio de estado resuelto) para durar 18 a 28 s hablados. "
            "Para 'historia': 1 o 2 frases breves de apoyo. Para 'post': lista vacía []. "
            "Para 'carrusel': de 3 a 6 láminas (una idea por lámina, 8 a 22 palabras cada una), en orden: "
            "el error común, lo que cuesta, el giro, cómo se resuelve paso a paso y cómo queda resuelto."
        ),
    },
    "cierre": {
        "type": "string",
        "description": (
            "Para 'video' el código pone SIEMPRE el cierre de venta ('No seas el Taller A. Sé el Taller B. "
            "Con El Socio, te lo solucionamos.'): aquí deja esa misma línea. Para 'historia': invitación "
            "a responder ('Responde esta historia con tu caso'). Para 'carrusel': la última lámina, una invitación "
            "corta a escribir por mensaje directo con su caso. Nunca 'link en bio' dentro de una pieza."
        ),
    },
    "caption": {
        "type": "string",
        "description": "Texto del pie de publicación en Instagram (2 a 4 líneas directas, sin hashtags basura ni cifras).",
    },
    "escena": {
        "type": "string",
        "enum": list(content_manager.ESCENAS),
        "description": "Escena isométrica para el Reel ('contraste', 'flujo', 'espacio3d', 'agenda').",
    },
    "etiquetas": {
        "type": "array",
        "items": {"type": "string"},
        "description": "De 2 a 4 etiquetas cortas (máx 18 caracteres cada una, cero números) para los tooltips/estados de la escena.",
    },
    "formato": {
        "type": "string",
        "enum": list(content_manager.FORMATOS_EN_ROTACION),
        "description": (
            "SOLO para 'video'. Cómo se va a VER el reel (la voz y el cierre son iguales en todos): "
            "'mundo' = ciudad isométrica, la cámara entra a los dos locales (ideal para contar un lugar: "
            "taller, obra, tienda, oficina) · 'collage' = recortes de papel, un objeto-metáfora por paso y "
            "la mascota de El Socio (ideal para explicar un proceso paso a paso: buscar clientes, correos, "
            "seguimiento, agenda) · 'duelo' = pantalla partida A arriba vs B abajo con medidores (ideal para "
            "un contraste directo frase por frase). El código no deja repetir el formato del reel anterior."
        ),
    },
    "planos": {
        "type": "array",
        "description": (
            "SOLO para 'video'. El storyboard: UN plano por frase, en orden (gancho, cada bloque, cierre). "
            "Cada plano dice qué muestra la cámara mientras la voz dice esa frase, y debe mostrar "
            "literalmente el sustantivo de la frase (si la voz dice 'pared', foco 'pared'). "
            "Para 'post' e 'historia': lista vacía []."
        ),
        "items": {
            "type": "object",
            "properties": {
                "toma": {"type": "string", "enum": list(content_manager.TOMAS),
                         "description": "ciudad (los dos locales de lejos) · pareja (los dos locales, más cerca) · calle (fachada de un local) · local (adentro, todo el cuarto) · detalle (zoom a un objeto)."},
                "lado": {"type": "string", "enum": ["A", "B"],
                         "description": "A = el negocio sin sistema (caos). B = el negocio con El Socio (orden)."},
                "foco": {"type": "string", "enum": sorted(content_manager.TODOS_LOS_FOCOS),
                         "description": "Objeto exacto que nombra la frase. taller: mesa, ficha, audios, maquinas, perchero, maniqui, lote, persona, pared · obra: pared, andamio, plano, sala, sofa, ventana, cables, persona · estudio: inventario, producto, luces, celular, camara, pantalla, ropa, persona · oficina: escritorio, pantalla, agenda, telefono, papeles, persona."},
                "estado": {"type": "string", "enum": list(content_manager.ESTADOS_PLANO),
                           "description": "caos (problema) u orden (resuelto). Por defecto A=caos, B=orden."},
                "tooltip": {"type": "string",
                            "description": "Etiqueta flotante sobre el foco, máx 26 caracteres, cero cifras (ej. 'A ciegas', 'Ficha exacta'). Opcional; úsala en 2 o 3 planos, no en todos."},
                "objeto": {"type": "string", "enum": list(content_manager.OBJETOS_COLLAGE),
                           "description": "Solo formato 'collage': el objeto-metáfora del paso. pecera = buscar clientes, iman = atraer, diana = cliente ideal, clasificadora = filtrar, tostadora = correos, embudo = seguimiento, agenda = reuniones, reloj = tiempo perdido, papeles = todo a mano, telefono = audios/whatsapp, etiqueta = presentar a El Socio, pantalla = sistema trabajando solo, ficha = ficha técnica, plano = remodelación/render, camara = fotos/catálogo, cajas = pedido/lote, maquina = producción."},
                "tarjeta": {"type": "string", "enum": list(content_manager.TARJETAS),
                            "description": "Tarjeta de interfaz flotante: correo, agenda, ficha, catalogo, render (antes/después), chat (audios sueltos), ninguna. Máx 2 por reel."},
            },
            # Con `strict`, la API exige `additionalProperties: false` en TODOS los objetos del
            # esquema, también en los anidados. Faltaba aquí y el cerebro de contenido ni siquiera
            # arrancaba: cada llamada volvía con HTTP 400 (se detectó en el primer día con clave real).
            "additionalProperties": False,
        },
    },
}

_CAMPOS_REQUERIDOS_PIEZA = [
    "tipo", "nicho", "gancho", "bloques", "cierre", "caption", "escena", "etiquetas"
]

HERRAMIENTA_PIEZA = [
    {
        "name": "proponer_pieza",
        "description": (
            "Entrega una única pieza lista para Instagram de El Socio (video Reel 1080x1920, "
            "post 1080x1350 o historia 1080x1920). Prohibido incluir cifras, precios, monedas, "
            "porcentajes o links externos."
        ),
        "input_schema": {
            "type": "object",
            "properties": _PROPIEDADES_PIEZA,
            "required": _CAMPOS_REQUERIDOS_PIEZA,
            "additionalProperties": False,
        },
        "strict": True,
    }
]

HERRAMIENTA_PLAN_DIARIO = [
    {
        "name": "proponer_plan_diario",
        "description": (
            "Entrega en una sola respuesta el lote completo de piezas faltantes del día "
            "(combinando Reels, Post, Historias y Carrusel con variedad de nichos y escenas, cero "
            "repetición de ganchos y cero cifras/precios/porcentajes/links)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "piezas": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": _PROPIEDADES_PIEZA,
                        "required": _CAMPOS_REQUERIDOS_PIEZA,
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["piezas"],
            "additionalProperties": False,
        },
        "strict": True,
    }
]

_CLAVES_ENV_CONTENIDO = (
    "CONTENT_MAX_DAILY_PIECES",
    "CONTENT_DAILY_VIDEOS",
    "CONTENT_DAILY_POSTS",
    "CONTENT_DAILY_STORIES",
    "CONTENT_DAILY_CAROUSELS",
    "CONTENT_SALES_RESERVE_USD",
    "CONTENT_MAX_DAILY_USD",
)


def cargar_config_contenido() -> dict[str, str]:
    cfg = sales_agent.cargar_config()
    if database.DB_PATH.exists():
        try:
            ajustes = database.get_settings()
            for clave in _CLAVES_ENV_CONTENIDO:
                k_bd = clave.lower()
                if ajustes.get(k_bd) and not cfg.get(clave):
                    cfg[clave] = str(ajustes[k_bd])
        except Exception:
            pass
    for clave in _CLAVES_ENV_CONTENIDO:
        if os.environ.get(clave):
            cfg[clave] = os.environ[clave]
    return cfg


def leer_config_contenido(cfg: dict[str, str]) -> dict[str, object]:
    base = sales_agent.leer_configuracion(cfg)
    max_videos = sales_agent._entero(cfg, "CONTENT_DAILY_VIDEOS", DEFAULT_DAILY_VIDEOS)
    max_posts = sales_agent._entero(cfg, "CONTENT_DAILY_POSTS", DEFAULT_DAILY_POSTS)
    max_historias = sales_agent._entero(cfg, "CONTENT_DAILY_STORIES", DEFAULT_DAILY_STORIES)
    max_carruseles = sales_agent._entero(cfg, "CONTENT_DAILY_CAROUSELS", DEFAULT_DAILY_CAROUSELS)
    suma_mix = max_videos + max_posts + max_historias + max_carruseles

    # Si `CONTENT_MAX_DAILY_PIECES` viene explícito (ej. "1" en pruebas o ajuste manual), manda él;
    # si no, el tope diario por defecto es la suma del mix orgánico (2 videos + 1 post + 2 historias = 5).
    tiene_max_explicito = bool(str(cfg.get("CONTENT_MAX_DAILY_PIECES") or "").strip())
    max_piezas = (
        sales_agent._entero(cfg, "CONTENT_MAX_DAILY_PIECES", suma_mix)
        if tiene_max_explicito else suma_mix
    )

    max_usd = float(base["max_usd"])
    reserva_defecto = 0.15 if max_usd >= 0.30 else round(max_usd * 0.25, 4)
    reserva_ventas = min(
        max_usd,
        sales_agent._decimal(cfg, "CONTENT_SALES_RESERVE_USD", reserva_defecto),
    )
    max_usd_contenido = min(
        max(0.0, max_usd - reserva_ventas),
        sales_agent._decimal(cfg, "CONTENT_MAX_DAILY_USD", 0.22),
    )

    base.update({
        "max_videos": max_videos,
        "max_posts": max_posts,
        "max_historias": max_historias,
        "max_carruseles": max_carruseles,
        "max_piezas": max_piezas,
        "tiene_max_explicito": tiene_max_explicito,
        "reserva_ventas_usd": reserva_ventas,
        "max_usd_contenido": max_usd_contenido,
        "colchon_piezas_listas": sales_agent._entero(cfg, "CONTENT_COLCHON_PIEZAS", 6),
    })
    return base


def calcular_faltantes_hoy(conf: dict[str, object]) -> list[str]:
    """Calcula la secuencia intercalada de formatos que faltan crear hoy por variedad."""
    max_total = int(conf["max_piezas"])
    if max_total <= 0:
        return []
    creadas_total = database.content_created_today() if database.DB_PATH.exists() else 0
    cupo_restante = max(0, max_total - creadas_total)
    if cupo_restante <= 0:
        return []

    por_tipo = (
        database.content_created_today_by_tipo()
        if database.DB_PATH.exists()
        else {"video": 0, "post": 0, "historia": 0, "carrusel": 0}
    )
    faltan_v = max(0, int(conf["max_videos"]) - int(por_tipo.get("video", 0)))
    faltan_p = max(0, int(conf["max_posts"]) - int(por_tipo.get("post", 0)))
    faltan_h = max(0, int(conf["max_historias"]) - int(por_tipo.get("historia", 0)))
    faltan_c = max(0, int(conf.get("max_carruseles", 0)) - int(por_tipo.get("carrusel", 0)))

    # Orden intercalado para variedad orgánica inmediata: Reel -> Historia -> Post -> Carrusel -> Reel...
    cola: list[str] = []
    while faltan_v > 0 or faltan_p > 0 or faltan_h > 0 or faltan_c > 0:
        if faltan_v > 0:
            cola.append("video")
            faltan_v -= 1
        if faltan_h > 0:
            cola.append("historia")
            faltan_h -= 1
        if faltan_p > 0:
            cola.append("post")
            faltan_p -= 1
        if faltan_c > 0:
            cola.append("carrusel")
            faltan_c -= 1

    # Si `CONTENT_MAX_DAILY_PIECES` se subió por encima de la suma por tipo, rellena alternando.
    ciclo_extra = ("video", "historia", "post")
    idx = 0
    while bool(conf.get("tiene_max_explicito")) and len(cola) < cupo_restante:
        cola.append(ciclo_extra[idx % len(ciclo_extra)])
        idx += 1

    return cola[:cupo_restante]


def construir_system_prompt_contenido() -> str:
    """Prompt estable cacheado (`ephemeral`) para pensar contenido con criterio de socio."""
    partes = [sales_agent.construir_system_prompt()]
    for ruta in (GUIA_VIDEO_FILE, FRASES_FILE):
        if ruta.exists():
            partes.append(ruta.read_text(encoding="utf-8").strip())
    partes.append(
        "## Tu rol ahora: Director Creativo Autónomo de El Socio\n"
        "- No eres un community manager genérico: hablas con voz de socio con estatus, calma y verdad incómoda.\n"
        "- Cada pieza nace de un dolor real de dueño de negocio (reprocesos, tiempo perdido, clientes que se van, "
        "ideas frenadas por no tener quién las ejecute).\n"
        "- PROHIBIDO usar palabras de precio o pago aunque no lleven cifra (la guarda en código las bloquea "
        "igual que un número): 'cuesta/cuestan', 'cobra/cobran/cobrar', 'vale/valen', 'tarifa', 'costo', "
        "'presupuesto', 'cotización', 'descuento', 'anticipo', 'abono', 'giro', 'transferencia/transferir', "
        "'consignar', 'link de pago' y nombres de pasarelas (Nequi, Bancolombia, PSE, etc.). Para decir que algo "
        "le sale caro al dueño en tiempo o reprocesos, usa palabras de desgaste ('se desgasta', 'se le va el día', "
        "'repite el trabajo', 'pierde el cliente'), nunca de dinero.\n"
        "- PROHIBIDO escribir números o dígitos (ni precios, ni porcentajes, ni '3 pasos', ni '10x'): "
        "si enumeras, usa palabras ('Primero', 'Luego', 'Resultado') sin caer en palabras de escala monetaria.\n"
        "- En Reels ('video'): estructura SIEMPRE un contraste A vs B rico de 5 a 7 bloques hablados "
        "(duración objetivo 18 a 28 segundos con voz neuronal humana). Empieza mostrando los dos lados o "
        "el error común, desarrolla el sistema paso a paso y remata con el cambio de estado visible.\n"
        "- En Historias ('historia'): impacto vertical directo y cercano de lectura rápida (gancho fuerte + "
        "1 o 2 líneas de apoyo en `bloques` + cierre invitando a responder la historia por mensaje directo).\n"
        "- En Posts ('post'): una sola verdad afilada para el feed (`bloques` vacío `[]`).\n"
        "- En Carruseles ('carrusel'): el formato que más se guarda y se comparte. Portada = gancho que "
        "obliga a deslizar; luego de 3 a 6 láminas en `bloques`, UNA idea por lámina, escritas para leer "
        "(no para la voz): el error común con un objeto concreto, lo que le cuesta al dueño, el giro, cómo "
        "lo resolvemos paso a paso y cómo queda. `cierre` = invitación corta a escribir por mensaje directo "
        "con su caso. Sin numerar láminas con dígitos (eso lo pone el diseño).\n"
        "- CLARIDAD PARA CUALQUIERA (sin excepción, en Reels/Historias/Carruseles/Posts): el motor usa "
        "palabras genéricas compartidas entre nichos como código interno de escena ('taller', 'estudio', "
        "'sesión', 'local', 'obra', 'oficina'). Quien ve la pieza no conoce ese código ni el nicho: la "
        "PRIMERA vez que el gancho o un bloque use una de esas palabras, tiene que ir pegada en la MISMA "
        "frase al sustantivo concreto que la hace entendible para cualquiera, hasta un niño ('sesión de "
        "fotos de tu producto', 'estudio fotográfico', 'taller de costura', 'obra de remodelación'). "
        "Nunca dejes 'la sesión', 'el taller' o 'el estudio' sueltos sin decir de qué son: si alguien que "
        "nunca oyó hablar del nicho se pregunta '¿sesión de qué?' o '¿cuál taller?', la pieza está mal "
        "escrita. Esto es más importante que sonar elegante o breve.\n"
        "- GANCHO de Reel: tensión en el primer segundo, con algo que se pierde ('Uno de estos dos talleres "
        "te va a arruinar la colección.', 'Uno de estos locales va a romper una pared de más.'). Nada de "
        "presentaciones ni preguntas tibias.\n"
        "- INTERACCIÓN MERECIDA, NO PEDIDA (la guarda en código rechaza la pieza completa si la pides): PROHIBIDO pedir comentario, like, guardado, compartido, seguimiento o 'link en bio' con cualquier palabra: 'comenta', 'dime abajo', 'dale like', 'pon un corazón', 'etiqueta a', 'comparte esto', 'guarda este', 'sígueme', 'activa las notificaciones'. Pedirlo sube el contador hoy y quema la credibilidad que es justo lo que estamos vendiendo. Para que la gente comente SIN que se lo pidas, todo Reel usa al menos uno de estos tres mecanismos:\n  1. DEJAR ALGO SIN CERRAR que el espectador quiera resolver: nombra el error pero no todo el remedio, o muestra el lado B sin decir el paso exacto que lo logró.\n  2. AFIRMAR ALGO DISCUTIBLE con lo que una parte del público no esté de acuerdo (una verdad incómoda del oficio que la mitad defiende y la mitad niega). Nada tibio: lo tibio no se comenta.\n  3. NOMBRAR UNA EXPERIENCIA ESPECÍFICA Y RECONOCIBLE que el espectador quiera completar con la suya (el detalle exacto que solo conoce quien lo vivió: el audio de voz a las once de la noche, la tela cortada al revés, el cliente que pide el cambio el viernes).\n"
        "- MOTIVO PARA GUARDAR (obligatorio en Reel y Carrusel): la pieza tiene que dejar algo APLICABLE que alguien quiera volver a ver — la secuencia de pasos del lado B, la señal temprana para detectar el problema, el criterio para decidir. Si la pieza solo describe un dolor sin dejar nada que el espectador pueda usar, NO sirve: el guardado es la métrica que el motor optimiza y una pieza sin motivo para guardarse nace con esa métrica en cero.\n"
        "- LA EXCEPCIÓN: invitar a escribir por mensaje directo con su caso SÍ se permite y se espera en Historias y Carruseles. Eso no es pedir interacción, es el paso de venta. La diferencia: pedir un like infla un contador, invitar a que te cuenten su caso abre una conversación que se puede cerrar.\n"
        "- CIERRE de Reel: venta, no despedida. Lo arma el código: 'No seas el Taller A. Sé el Taller B. "
        "Con El Socio, te lo solucionamos.' Por eso el lado A y el lado B tienen que quedar clarísimos en los bloques.\n"
        "- FORMATO de Reel (`formato`): 'mundo' para contar un lugar, 'collage' para explicar un proceso paso a "
        "paso con objetos-metáfora, 'duelo' para un contraste frase a frase. Elige el que mejor cuente ESA idea; "
        "el código rota para que nunca salgan dos iguales seguidos. En 'collage' cada plano lleva su `objeto`.\n"
        "- En Reels, escribe también `planos` (el storyboard): un plano por frase. Piensa como director, "
        "no como redactor: por cada frase pregúntate QUÉ SE VE mientras la voz la dice. La imagen debe "
        "mostrar el sustantivo exacto de la frase (voz 'taller' → se ve el taller; voz 'pared' → la cámara "
        "en la pared). Gancho en toma 'ciudad' o 'pareja' si plantea dos negocios; lado A = caos con "
        "objetos concretos del problema; lado B = el mismo lugar resuelto; cierre en 'pareja'. Nunca dos "
        "planos seguidos con la misma toma y el mismo foco. Escribe frases con objetos visibles "
        "(audios, ficha, pared, cajas, bandeja, agenda), no abstracciones ('optimizar', 'procesos').\n"
        "- VOZ HABLADA (ADN Raymond — skill `humanizacion-el-socio`): escribe cada bloque para el oído, "
        "no para leer en diapositivas. Tuteo natural colombiano sin caricatura, verbos cotidianos "
        "('cuadrar', 'toca repetir', 'mandar', 'quitarse de encima'), enumeraciones corridas en una "
        "sola respiración (evita cortar una misma acción en micro-frases sueltas con punto seguido) y "
        "pivote limpio al pasar de A a B ('En el segundo, ...', 'Pero con nosotros, ...', 'En cambio, ...'). "
        "Usa máximo 1 expresión real por Reel ('la verdad', 'básicamente', 'sí, obvio' o una pregunta "
        "retórica corta), cero palabrería de IA o folleto, y remata seco sin tono de comercial."
    )
    return "\n\n".join(partes)


def _leer_resultados_limpios(ruta: Path | None = None) -> str:
    ruta = RESULTADOS_FILE if ruta is None else ruta
    if not ruta.exists():
        return "(sin historial todavía)"
    lineas_ok: list[str] = []
    for linea in ruta.read_text(encoding="utf-8").splitlines()[-25:]:
        texto = linea.strip()
        if not texto or texto.startswith("<!--"):
            continue
        if sales_agent.revisar_guarda_precios(texto):
            continue
        lineas_ok.append(texto)
    return "\n".join(lineas_ok[-15:]) or "(sin filas recientes)"


def elegir_formato_sugerido(conf: dict[str, object] | None = None) -> str:
    """Elige el siguiente formato pendiente del mix diario (2 Reels + 1 Post + 2 Historias)."""
    if conf is not None:
        faltantes = calcular_faltantes_hoy(conf)
        if faltantes:
            return faltantes[0]
    recientes = database.list_content(limit=5) if database.DB_PATH.exists() else []
    tipos_rec = [str(p.get("tipo") or "") for p in recientes]
    if tipos_rec[:2] == ["video", "video"]:
        return "historia" if "historia" not in tipos_rec[:3] else "post"
    if len(tipos_rec) >= 1 and tipos_rec[0] == "video" and "historia" not in tipos_rec[:2]:
        return "historia"
    return "video"


def construir_contexto_creativo(*, tipo_forzado: str = "", formatos_lote: list[str] | None = None) -> str:
    nichos_txt = sales_agent.cargar_todos_los_nichos_sin_precios() or "(usa enfoque universal para dueños de negocio)"
    resultados_txt = _leer_resultados_limpios()
    senales = database.list_recent_market_signals(limit=10) if database.DB_PATH.exists() else {"landing": [], "respuestas": []}
    ganchos_usados = database.list_recent_hooks(limit=45) if database.DB_PATH.exists() else []
    nichos_video_bloqueados = database.list_recent_video_nichos(dias=DIAS_SIN_REPETIR_TEMA_VIDEO) if database.DB_PATH.exists() else set()
    escenas_usadas_hoy = content_manager.escenas_usadas_hoy() if database.DB_PATH.exists() else set()

    if formatos_lote:
        encabezado = (
            f"Plan diario requerido ahora ({len(formatos_lote)} piezas en este orden exacto de `tipo`): "
            + ", ".join(f"**{t}**" for t in formatos_lote)
            + ". Varía los nichos, los ángulos y las escenas isométricas ('contraste', 'flujo', 'espacio3d', 'agenda') "
            "para que cada pieza del día ataque un dolor distinto."
        )
    else:
        formato = tipo_forzado if tipo_forzado in database.CONTENT_TIPOS else elegir_formato_sugerido()
        encabezado = f"Formato requerido hoy: **{formato}**."

    partes = [
        encabezado,
        f"Nichos activos (sin precios):\n{nichos_txt}",
        f"Aprendizaje real de mercado hasta hoy:\n{resultados_txt}",
    ]
    if senales["landing"] or senales["respuestas"]:
        muestras = senales["landing"][:5] + senales["respuestas"][:5]
        limpias = [m for m in muestras if not sales_agent.revisar_guarda_precios(m)]
        if limpias:
            partes.append("Dolores y preguntas reales que escribieron prospectos:\n- " + "\n- ".join(limpias))
    if ganchos_usados:
        partes.append(
            "PROHIBIDO repetir o parecerse a cualquiera de estos ganchos ya usados:\n- "
            + "\n- ".join(ganchos_usados[:35])
        )
    if nichos_video_bloqueados:
        partes.append(
            f"PROHIBIDO usar `nicho` para un REEL (video) si aparece en esta lista: ya se usó en "
            f"otro REEL en los últimos {DIAS_SIN_REPETIR_TEMA_VIDEO} días: "
            + ", ".join(sorted(nichos_video_bloqueados))
            + ". (Un post, historia o carrusel sí puede reforzar ese mismo nicho; la regla es solo entre REELS.)"
        )
    if formatos_lote and sum(1 for t in formatos_lote if t == "video") > 1:
        partes.append(
            "Si hoy hay más de un REEL en el plan, cada REEL tiene que ir de un `nicho` distinto entre sí."
        )
    escenas_libres = [e for e in content_manager.ESCENAS if e not in escenas_usadas_hoy]
    if escenas_usadas_hoy and escenas_libres:
        partes.append(
            f"PROHIBIDO repetir `escena` entre piezas de hoy (cualquier tipo): ya se usaron "
            f"{', '.join(sorted(escenas_usadas_hoy))}. Usa solo de las que quedan libres: "
            + ", ".join(escenas_libres)
        )

    if formatos_lote:
        partes.append(
            f"Llama a `proponer_plan_diario` entregando exactamente {len(formatos_lote)} piezas con "
            "ganchos completamente distintos entre sí, cero cifras, cero precios, cero porcentajes y cero humo."
        )
    else:
        partes.append(
            "Crea UNA pieza nueva que frene el scroll en el primer segundo, ataque un dolor real "
            "y termine llevando al prospecto a contar su problema. Cero cifras, cero precios, cero humo."
        )
    return "\n\n".join(partes)


class CerebroContenido:
    def __init__(self, cfg: dict[str, str] | None = None, *, dry_run: bool = False, con_api: bool = False):
        self.cfg = cargar_config_contenido() if cfg is None else cfg
        self.dry_run = dry_run
        self.con_api = con_api and dry_run
        self.simulado = dry_run and not self.con_api
        self.conf = leer_config_contenido(self.cfg)
        self.modelo = str(self.conf["modelo"])
        self.costo_corrida = 0.0
        self.turno = 0

    def _gasto_hoy_usd(self) -> float:
        base = database.agent_cost_today_usd() if database.DB_PATH.exists() else 0.0
        return base + (self.costo_corrida if self.dry_run else 0.0)

    def _gasto_contenido_hoy_usd(self) -> float:
        base = database.agent_content_cost_today_usd() if database.DB_PATH.exists() else 0.0
        return base + (self.costo_corrida if self.dry_run else 0.0)

    def _techo_compartido_para_contenido(self) -> float:
        """Techo máximo del gasto total diario que contenido puede tocar (protegiendo reserva de ventas)."""
        max_usd = float(self.conf["max_usd"])
        reserva = float(self.conf["reserva_ventas_usd"])
        if database.DB_PATH.exists():
            # Si hay seguimientos vencidos esperando turno de ventas, blinda colchón extra.
            pendientes_ventas = len(database.list_due_followups(limit=3))
            if pendientes_ventas > 0:
                reserva = min(max_usd, reserva + 0.05)
        return round(max(0.0, max_usd - reserva), 6)

    def _log(self, herramienta: str, *, argumentos: str = "", resultado: str = "",
             uso: dict | None = None, costo_usd: float = 0.0, bloqueado: str = "") -> None:
        if self.dry_run:
            return
        u = uso or {}
        database.log_agent_action(
            lead_id=None,
            turno=self.turno,
            modelo=self.modelo,
            herramienta=herramienta,
            argumentos=argumentos,
            resultado=resultado,
            tokens_entrada=int(u.get("input_tokens", 0)),
            tokens_salida=int(u.get("output_tokens", 0)),
            tokens_cache_creacion=int(u.get("cache_creation_input_tokens", 0)),
            tokens_cache_lectura=int(u.get("cache_read_input_tokens", 0)),
            costo_usd=costo_usd,
            bloqueado_por_guarda=bloqueado,
        )

    def guardas_previas(self) -> str:
        """Verifica llaves, cuota diaria de contenido y prioridad de ventas sobre los 0.50 USD."""
        if self.simulado:
            return ""
        if not self.conf["tiene_api_key"]:
            return "Falta ANTHROPIC_API_KEY en .env — el cerebro de contenido no llama a la API."
        creadas = database.content_created_today()
        if creadas >= int(self.conf["max_piezas"]):
            return f"Cuota diaria de contenido ya cumplida ({creadas}/{self.conf['max_piezas']})."

        # Pensar una pieza cuesta saldo; publicarla no. Si la despensa ya tiene para varios
        # días, ese saldo rinde más en correos. Se vuelve a crear cuando la cola baja sola.
        colchon = int(self.conf.get("colchon_piezas_listas") or 0)
        if colchon > 0 and database.DB_PATH.exists():
            listas = len(database.list_content(estado="generado", limit=colchon + 1))
            if listas >= colchon:
                return (f"Ya hay {listas} piezas listas sin publicar (colchón {colchon}). "
                        "El saldo rinde más en correos hasta que baje la cola.")

        max_usd = float(self.conf["max_usd"])
        gastado = self._gasto_hoy_usd()
        if gastado >= max_usd:
            return (f"Tope diario compartido alcanzado ({gastado:.4f}/{max_usd:.2f} USD). "
                    "Vender va primero que publicar.")

        techo_con_reserva = self._techo_compartido_para_contenido()
        if gastado >= techo_con_reserva:
            return (f"Reserva de saldo protegida para ventas ({gastado:.4f}/{max_usd:.2f} USD). "
                    "Vender va primero que publicar.")

        gastado_cont = self._gasto_contenido_hoy_usd()
        max_cont = float(self.conf["max_usd_contenido"])
        if max_cont > 0 and gastado_cont >= max_cont:
            return (f"Sub-tope diario de contenido alcanzado ({gastado_cont:.4f}/{max_cont:.2f} USD). "
                    "Vender va primero que publicar.")
        return ""

    def _presupuesto_agotado_en_loop(self) -> bool:
        if self._gasto_hoy_usd() >= float(self.conf["max_usd"]):
            return True
        if self._gasto_hoy_usd() >= self._techo_compartido_para_contenido():
            return True
        max_cont = float(self.conf["max_usd_contenido"])
        if max_cont > 0 and self._gasto_contenido_hoy_usd() >= max_cont:
            return True
        return False

    def _encolar_propuesta(self, propuesta_valida: dict, *, aprobar: bool) -> int:
        enc = content_manager.encolar(
            tipo=propuesta_valida["tipo"],
            gancho=propuesta_valida["gancho"],
            guion=propuesta_valida["guion"],
            caption=propuesta_valida["caption_completo"],
            nicho=propuesta_valida["nicho"],
            nota="creado por content_brain",
            escena=propuesta_valida["escena"],
            etiquetas=propuesta_valida["etiquetas"],
            planos=propuesta_valida.get("planos") or None,
            formato=propuesta_valida.get("formato") or "",
        )
        content_id = int(enc["id"])
        if aprobar:
            database.update_content(content_id, estado="aprobado")
        self._log(
            "content_brain_pieza",
            argumentos=json.dumps({"id": content_id, "tipo": propuesta_valida["tipo"],
                                   "gancho": propuesta_valida["gancho"]}, ensure_ascii=False),
            resultado=f"encolada #{content_id}",
        )
        return content_id

    def _renderizar_pendientes_aprobadas(self, *, max_renders_video: int = 1) -> list[dict[str, object]]:
        """Renderiza piezas `aprobado` ya pensadas (posts/historias al instante; videos con cupo por latido)."""
        if self.dry_run or not database.DB_PATH.exists():
            return []
        aprobadas = list(reversed(database.list_content(estado="aprobado", limit=15)))
        resultados: list[dict[str, object]] = []
        videos_hechos = 0
        for p in aprobadas:
            es_video = p.get("tipo") == "video"
            if es_video and videos_hechos >= max(0, max_renders_video):
                continue
            gen = content_manager.generar(int(p["id"]))
            if es_video:
                videos_hechos += 1
            resultados.append({
                "id": int(p["id"]),
                "tipo": p.get("tipo"),
                "generado": bool(gen.get("generado")),
                "archivo": gen.get("archivo", ""),
            })
        return resultados

    def crear_pieza_del_dia(
        self, *, tipo_forzado: str = "", renderizar: bool = True, aprobar: bool = True,
    ) -> dict[str, object]:
        bloqueo = self.guardas_previas()
        if bloqueo:
            return {"ok": False, "creada": False, "motivo": bloqueo, "costo_usd": 0.0}

        formato_elegido = (
            tipo_forzado if tipo_forzado in database.CONTENT_TIPOS
            else elegir_formato_sugerido(self.conf)
        )
        system_prompt = construir_system_prompt_contenido()
        contexto = construir_contexto_creativo(tipo_forzado=formato_elegido)

        if self.simulado:
            return {
                "ok": True,
                "creada": False,
                "dry_run": True,
                "motivo": "dry_run_sin_api",
                "formato_sugerido": formato_elegido,
                "faltantes_hoy": calcular_faltantes_hoy(self.conf),
                "caracteres_prompt": len(system_prompt),
                "costo_usd": 0.0,
            }

        api_key = (self.cfg.get("ANTHROPIC_API_KEY") or "").strip()
        mensajes: list[dict] = [{"role": "user", "content": contexto}]
        ganchos_previos = {g.lower().strip() for g in database.list_recent_hooks(limit=60)}
        nichos_video_bloqueados = database.list_recent_video_nichos(dias=DIAS_SIN_REPETIR_TEMA_VIDEO)
        escenas_usadas_hoy = content_manager.escenas_usadas_hoy()
        propuesta_valida: dict | None = None
        ultimo_error = "sin_propuesta"

        while self.turno < MAX_TURNOS_CONTENIDO:
            if self._presupuesto_agotado_en_loop():
                ultimo_error = "tope_gasto"
                break
            self.turno += 1
            cuerpo = {
                "model": self.modelo,
                "max_tokens": MAX_TOKENS_CONTENIDO,
                "system": [{"type": "text", "text": system_prompt,
                            "cache_control": {"type": "ephemeral"}}],
                "tools": HERRAMIENTA_PIEZA,
                "messages": mensajes,
                "output_config": {"effort": "low"},
            }
            try:
                respuesta = sales_agent.llamar_api(api_key, cuerpo)
            except sales_agent.ErrorAPI as err:
                self._log("content_brain_error", resultado=str(err)[:400])
                return {"ok": False, "creada": False, "motivo": f"API: {err}",
                        "costo_usd": round(self.costo_corrida, 6)}

            uso = respuesta.get("usage", {}) or {}
            costo = sales_agent.calcular_costo_usd(self.modelo, uso)
            self.costo_corrida += costo
            self._log("content_brain_api", resultado=f"stop={respuesta.get('stop_reason')}",
                      uso=uso, costo_usd=costo)

            contenido = respuesta.get("content", []) or []
            mensajes.append({"role": "assistant", "content": contenido})
            tools = [b for b in contenido if b.get("type") == "tool_use" and b.get("name") == "proponer_pieza"]
            if not tools:
                ultimo_error = "modelo_no_llamo_proponer_pieza"
                break

            bloque = tools[0]
            datos = bloque.get("input") or {}
            ok_pieza, detalle_o_limpia = self._validar_propuesta(
                datos, ganchos_previos, nichos_video_bloqueados=nichos_video_bloqueados,
                escenas_usadas_hoy=escenas_usadas_hoy,
            )
            if ok_pieza and isinstance(detalle_o_limpia, dict):
                propuesta_valida = detalle_o_limpia
                break

            motivo_txt = str(detalle_o_limpia)
            ultimo_error = motivo_txt
            self._log("content_brain_bloqueado",
                      argumentos=json.dumps(datos, ensure_ascii=False),
                      resultado="rechazado por guarda", bloqueado=motivo_txt)
            mensajes.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": bloque.get("id"),
                    "content": (
                        f"RECHAZADO por guarda en código: {motivo_txt}. "
                        "Propón otra pieza completamente libre de números, precios, porcentajes, "
                        "monedas, links y sin repetir ganchos previos."
                    ),
                    "is_error": True,
                }],
            })

        if not propuesta_valida:
            return {"ok": False, "creada": False, "motivo": ultimo_error,
                    "costo_usd": round(self.costo_corrida, 6)}

        if self.dry_run:
            return {
                "ok": True, "creada": False, "dry_run": True,
                "propuesta": propuesta_valida,
                "costo_usd": round(self.costo_corrida, 6),
            }

        content_id = self._encolar_propuesta(propuesta_valida, aprobar=aprobar)
        salida: dict[str, object] = {
            "ok": True, "creada": True, "id": content_id,
            "tipo": propuesta_valida["tipo"], "gancho": propuesta_valida["gancho"],
            "costo_usd": round(self.costo_corrida, 6),
        }
        if renderizar:
            gen = content_manager.generar(content_id)
            salida["generado"] = bool(gen.get("generado"))
            salida["archivo"] = gen.get("archivo", "")
            if not gen.get("generado"):
                salida["error_render"] = gen.get("error", "")
        return salida

    def planear_y_crear_lote_diario(
        self, *, renderizar: bool = True, aprobar: bool = True, max_renders_video: int = 1,
    ) -> dict[str, object]:
        """Planea en una sola llamada eficiente el mix diario faltante (ej. 2 Reels + 1 Post + 2 Historias)
        y renderiza sin ahogar el presupuesto compartido ni bloquear el ciclo comercial.
        """
        faltantes = calcular_faltantes_hoy(self.conf)
        if self.simulado:
            return {
                "ok": True,
                "creadas": 0,
                "dry_run": True,
                "motivo": "dry_run_sin_api",
                "faltantes_hoy": faltantes,
                "cuota_diaria": {
                    "video": self.conf["max_videos"],
                    "post": self.conf["max_posts"],
                    "historia": self.conf["max_historias"],
                    "carrusel": self.conf["max_carruseles"],
                    "total": self.conf["max_piezas"],
                },
                "costo_usd": 0.0,
            }

        # Si ya no faltan piezas por pensar hoy, igual adelanta renders pendientes (0 USD).
        if not faltantes:
            renders_pend = self._renderizar_pendientes_aprobadas(max_renders_video=max_renders_video) if renderizar else []
            return {
                "ok": True,
                "creadas": 0,
                "motivo": f"Cuota diaria ya planeada ({self.conf['max_piezas']}).",
                "renderizadas_pendientes": renders_pend,
                "costo_usd": 0.0,
            }

        bloqueo = self.guardas_previas()
        if bloqueo:
            renders_pend = self._renderizar_pendientes_aprobadas(max_renders_video=max_renders_video) if renderizar else []
            return {
                "ok": False, "creadas": 0, "motivo": bloqueo,
                "renderizadas_pendientes": renders_pend, "costo_usd": 0.0,
            }

        # Si solo falta 1 pieza, usa el flujo unitario directo.
        if len(faltantes) == 1:
            unica = self.crear_pieza_del_dia(
                tipo_forzado=faltantes[0], renderizar=False, aprobar=aprobar,
            )
            renders = self._renderizar_pendientes_aprobadas(max_renders_video=max_renders_video) if renderizar else []
            unica["creadas"] = 1 if unica.get("creada") else 0
            unica["renderizadas"] = renders
            return unica

        system_prompt = construir_system_prompt_contenido()
        contexto = construir_contexto_creativo(formatos_lote=faltantes)
        api_key = (self.cfg.get("ANTHROPIC_API_KEY") or "").strip()
        mensajes: list[dict] = [{"role": "user", "content": contexto}]
        ganchos_previos = {g.lower().strip() for g in database.list_recent_hooks(limit=60)}
        # Crece también dentro de este mismo lote: 2 reels del mismo día no pueden compartir nicho,
        # pero un post/historia/carrusel sí puede reforzar el nicho de un reel del día (no se le suma aquí).
        nichos_video_bloqueados = database.list_recent_video_nichos(dias=DIAS_SIN_REPETIR_TEMA_VIDEO)
        escenas_usadas_hoy = content_manager.escenas_usadas_hoy()

        aceptadas: list[dict] = []
        pendientes_pedir = list(faltantes)
        ultimo_error = "sin_propuestas"

        while self.turno < MAX_TURNOS_CONTENIDO and pendientes_pedir:
            if self._presupuesto_agotado_en_loop():
                ultimo_error = "tope_gasto"
                break
            self.turno += 1
            cuerpo = {
                "model": self.modelo,
                "max_tokens": MAX_TOKENS_PLAN_DIARIO,
                "system": [{"type": "text", "text": system_prompt,
                            "cache_control": {"type": "ephemeral"}}],
                "tools": HERRAMIENTA_PLAN_DIARIO,
                "messages": mensajes,
                "output_config": {"effort": "low"},
            }
            try:
                respuesta = sales_agent.llamar_api(api_key, cuerpo)
            except sales_agent.ErrorAPI as err:
                self._log("content_brain_error", resultado=str(err)[:400])
                ultimo_error = f"API: {err}"
                break

            uso = respuesta.get("usage", {}) or {}
            costo = sales_agent.calcular_costo_usd(self.modelo, uso)
            self.costo_corrida += costo
            self._log("content_brain_plan_api", resultado=f"stop={respuesta.get('stop_reason')}",
                      uso=uso, costo_usd=costo)

            contenido = respuesta.get("content", []) or []
            mensajes.append({"role": "assistant", "content": contenido})
            tools = [b for b in contenido if b.get("type") == "tool_use" and b.get("name") == "proponer_plan_diario"]
            if not tools:
                ultimo_error = "modelo_no_llamo_proponer_plan_diario"
                break

            bloque = tools[0]
            crudas = (bloque.get("input") or {}).get("piezas") or []
            errores_lote: list[str] = []
            restantes_por_tipo: dict[str, int] = {}
            for t in pendientes_pedir:
                restantes_por_tipo[t] = restantes_por_tipo.get(t, 0) + 1

            for idx_p, item in enumerate(crudas):
                if len(aceptadas) >= len(faltantes):
                    break
                ok_p, det = self._validar_propuesta(
                    item or {}, ganchos_previos, nichos_video_bloqueados=nichos_video_bloqueados,
                    escenas_usadas_hoy=escenas_usadas_hoy,
                )
                if not ok_p or not isinstance(det, dict):
                    errores_lote.append(f"pieza {idx_p + 1}: {det}")
                    continue
                t_pieza = det["tipo"]
                if restantes_por_tipo.get(t_pieza, 0) <= 0:
                    continue
                restantes_por_tipo[t_pieza] -= 1
                ganchos_previos.add(det["gancho"].lower().strip())
                escenas_usadas_hoy.add(det["escena"])
                if t_pieza == "video":
                    nichos_video_bloqueados.add(det["nicho"].lower().strip())
                aceptadas.append(det)

            nuevos_pendientes: list[str] = []
            for t in ("video", "historia", "post", "carrusel"):
                nuevos_pendientes.extend([t] * max(0, restantes_por_tipo.get(t, 0)))
            pendientes_pedir = nuevos_pendientes

            if not pendientes_pedir:
                break

            ultimo_error = "; ".join(errores_lote[:4]) or "faltaron piezas válidas en el plan"
            self._log("content_brain_bloqueado",
                      argumentos=json.dumps({"pendientes": pendientes_pedir}, ensure_ascii=False),
                      resultado="reintento parcial de lote", bloqueado=ultimo_error[:300])
            mensajes.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": bloque.get("id"),
                    "content": (
                        f"Algunas piezas fueron rechazadas ({ultimo_error}). "
                        f"Entrega ÚNICAMENTE las {len(pendientes_pedir)} piezas faltantes de tipos "
                        f"{pendientes_pedir}, cero números/precios/porcentajes/links y sin repetir ganchos."
                    ),
                    "is_error": True,
                }],
            })

        if not aceptadas:
            return {"ok": False, "creadas": 0, "motivo": ultimo_error,
                    "costo_usd": round(self.costo_corrida, 6)}

        if self.dry_run:
            return {
                "ok": True, "creadas": 0, "dry_run": True,
                "propuestas": aceptadas,
                "costo_usd": round(self.costo_corrida, 6),
            }

        ids_creados: list[dict[str, object]] = []
        for prop in aceptadas:
            cid = self._encolar_propuesta(prop, aprobar=aprobar)
            ids_creados.append({"id": cid, "tipo": prop["tipo"], "gancho": prop["gancho"]})

        renders = self._renderizar_pendientes_aprobadas(max_renders_video=max_renders_video) if renderizar else []
        return {
            "ok": True,
            "creadas": len(ids_creados),
            "piezas": ids_creados,
            "renderizadas": renders,
            "costo_usd": round(self.costo_corrida, 6),
        }

    def _validar_propuesta(
        self, datos: dict, ganchos_previos: set[str], *,
        nichos_video_bloqueados: set[str] | None = None,
        escenas_usadas_hoy: set[str] | None = None,
    ) -> tuple[bool, dict | str]:
        tipo = str(datos.get("tipo") or "video").strip().lower()
        if tipo not in database.CONTENT_TIPOS:
            return False, f"tipo inválido: {tipo}"
        gancho = " ".join(str(datos.get("gancho") or "").split()).strip()
        if not gancho:
            return False, "gancho vacío"
        if gancho.lower() in ganchos_previos:
            return False, f"gancho repetido: '{gancho}'"

        bloques_raw = datos.get("bloques") or []
        bloques = [" ".join(str(b).split()).strip() for b in bloques_raw if str(b).strip()][:content_manager.MAX_BLOQUES]
        if tipo == "video" and len(bloques) < 2:
            return False, "un video Reel necesita al menos 2 bloques de desarrollo"
        if tipo == "carrusel":
            if len(bloques) < content_manager.MIN_LAMINAS_CARRUSEL:
                return False, (f"un carrusel necesita al menos {content_manager.MIN_LAMINAS_CARRUSEL} "
                               "láminas de desarrollo en `bloques`")
            bloques = bloques[:content_manager.MAX_LAMINAS_CARRUSEL]

        cierre_defecto = {
            "historia": "Responde esta historia con tu caso",
            "carrusel": content_manager.CIERRE_CARRUSEL_DEFECTO,
        }.get(tipo, content_manager.LINEA_MARCA)
        cierre = " ".join(str(datos.get("cierre") or cierre_defecto).split()).strip()
        caption = str(datos.get("caption") or "").strip()
        nicho = " ".join(str(datos.get("nicho") or "general").split()).strip()[:60]
        nicho_clave = nicho.lower()
        if tipo == "video" and nicho_clave in (nichos_video_bloqueados or set()):
            return False, (f"tema de video repetido: '{nicho}' ya se usó en otro REEL en los últimos "
                            f"{DIAS_SIN_REPETIR_TEMA_VIDEO} días (otros formatos sí pueden reforzar el mismo nicho)")

        try:
            escena = content_manager.normalizar_escena(str(datos.get("escena") or "contraste"))
            etiquetas = content_manager.normalizar_etiquetas(
                [str(x).replace("|", " ").replace(";", " ")[:content_manager.MAX_LARGO_ETIQUETA]
                 for x in (datos.get("etiquetas") or [])]
            )
        except ValueError as exc:
            return False, str(exc)

        usadas_hoy = escenas_usadas_hoy or set()
        # Si ya se usaron las 4 escenas hoy no hay de otra: se deja repetir en vez de trabar el día.
        if escena in usadas_hoy and len(usadas_hoy) < len(content_manager.ESCENAS):
            return False, (f"escena visual repetida: '{escena}' ya se usó hoy en otra pieza "
                            f"(quedan libres: {', '.join(e for e in content_manager.ESCENAS if e not in usadas_hoy)})")

        planos = content_manager.normalizar_planos(datos.get("planos") or []) if tipo == "video" else []

        if tipo == "carrusel":
            # La última línea del guion es la lámina de cierre (ver `content_manager.laminas_carrusel`).
            guion = "\n".join([*bloques, cierre])
        else:
            guion = "\n".join(bloques) if tipo in ("video", "historia") else ""
        motivos = sales_agent.revisar_guarda_precios(
            gancho, guion, cierre, caption, *etiquetas, *content_manager.tooltips_de(planos))
        if motivos:
            return False, "; ".join(motivos[:5])

        caption_completo = cierre if tipo == "historia" else (caption or cierre)
        return True, {
            "tipo": tipo,
            "nicho": nicho,
            "gancho": gancho,
            "guion": guion,
            "cierre": cierre,
            "caption_completo": caption_completo,
            "escena": escena,
            "etiquetas": etiquetas,
            "planos": planos,
            "formato": str(datos.get("formato") or "").strip().lower() if tipo == "video" else "",
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cerebro autónomo de contenido de El Socio.")
    parser.add_argument("--tipo", choices=["", "post", "video", "historia", "carrusel"], default="",
                        help="Forzar 'post', 'video' o 'historia' (vacío = elige automático).")
    parser.add_argument("--plan-diario", action="store_true",
                        help="Planea y encola todo el lote diario faltante en una sola llamada.")
    parser.add_argument("--sin-render", action="store_true",
                        help="Solo pensar y encolar en BD sin llamar al render.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Valida en seco: 0 tokens, 0 BD, 0 render.")
    parser.add_argument("--con-api", action="store_true",
                        help="Junto a --dry-run: prueba el modelo sin guardar ni renderizar.")
    args = parser.parse_args(argv)

    if not args.dry_run or args.con_api:
        database.init_db()

    cerebro = CerebroContenido(dry_run=args.dry_run, con_api=args.con_api)
    if args.plan_diario and not args.tipo:
        res = cerebro.planear_y_crear_lote_diario(
            renderizar=not args.sin_render, max_renders_video=2,
        )
    else:
        res = cerebro.crear_pieza_del_dia(
            tipo_forzado=args.tipo, renderizar=not args.sin_render,
        )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
