#!/usr/bin/env python3
"""Cerebro autónomo de contenido de El Socio (Paso 3/3). Solo Python stdlib.

Piensa por sí solo qué publicar hoy (post o Reel vertical con voz humana),
basándose en:
  - `contexto/identidad.md` + `contexto/MODO_TRABAJO.md`
  - `contexto/guia-estilo-video.md` + `redes/FRASES.md`
  - las skills de calidad (`humanizer`, `psicologia-y-estatus`, `editor-implacable`)
  - dolores reales de `nichos/*.md` (recortados sin precios en código)
  - aprendizaje real en `contexto/RESULTADOS_MERCADO.md`
  - dudas reales recibidas en `landing_messages` y `processed_replies` (sin PII)
  - ganchos ya usados en `content_queue` (prohibido repetir)

Reglas duras en código:
  1. Comparte el MISMO tope diario de USD (`SALES_AGENT_MAX_DAILY_USD`, 0.50 USD)
     que `sales_agent.py` en `agent_log`. Vender siempre va antes que publicar.
  2. Tope diario de piezas creadas (`CONTENT_MAX_DAILY_PIECES`, por defecto 1).
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
MAX_TOKENS_CONTENIDO = 1400

HERRAMIENTA_PIEZA = [
    {
        "name": "proponer_pieza",
        "description": (
            "Entrega una única pieza lista para Instagram de El Socio (post 1080x1350 "
            "o video Reel 1080x1920 con locución humana y escena isométrica). "
            "Prohibido incluir cifras, precios, monedas, porcentajes o links externos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo": {
                    "type": "string",
                    "enum": ["video", "post"],
                    "description": "Formato de la pieza ('video' = Reel vertical con voz; 'post' = imagen frase).",
                },
                "nicho": {
                    "type": "string",
                    "description": "Nicho al que habla (ej. 'general', 'fichas-tecnicas-ropa', 'modelado-3d-espacios').",
                },
                "gancho": {
                    "type": "string",
                    "description": "Frase inicial contundente (máx 12 palabras, sin cifras, presente desde el frame 1).",
                },
                "bloques": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "De 2 a 4 bloques cortos (2 a 6 palabras cada uno) para el desarrollo del Reel. Vacío si es post.",
                },
                "cierre": {
                    "type": "string",
                    "description": "Llamado a la acción sobrio al pie del Reel (ej. 'Cuéntanos tu problema · link en bio').",
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
                    "description": "De 1 a 3 etiquetas cortas (máx 18 caracteres cada una, cero números) para los tooltips de la escena.",
                },
            },
            "required": [
                "tipo", "nicho", "gancho", "bloques", "cierre", "caption", "escena", "etiquetas"
            ],
            "additionalProperties": False,
        },
        "strict": True,
    }
]


def cargar_config_contenido() -> dict[str, str]:
    cfg = sales_agent.cargar_config()
    for clave in ("CONTENT_MAX_DAILY_PIECES",):
        if os.environ.get(clave):
            cfg[clave] = os.environ[clave]
    return cfg


def leer_config_contenido(cfg: dict[str, str]) -> dict[str, object]:
    base = sales_agent.leer_configuracion(cfg)
    base["max_piezas"] = sales_agent._entero(cfg, "CONTENT_MAX_DAILY_PIECES", 1)
    return base


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
        "- PROHIBIDO escribir números o dígitos (ni precios, ni porcentajes, ni '3 pasos', ni '10x'): "
        "si enumeras, usa palabras ('Primero', 'Segundo', 'Resultado') sin caer en palabras de escala monetaria.\n"
        "- En Reels ('video'), el gancho, los bloques y el cierre serán HABLADOS por una voz humana neuronal: "
        "escríbelos con ritmo oral natural, frases cortas y contundentes.\n"
        "- Llama siempre a la herramienta `proponer_pieza` y termina."
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
        # Evitar pasar números grandes que confundan al modelo.
        if sales_agent.revisar_guarda_precios(texto):
            continue
        lineas_ok.append(texto)
    return "\n".join(lineas_ok[-15:]) or "(sin filas recientes)"


def elegir_formato_sugerido() -> str:
    """Prioriza Reels verticales con voz (3 de cada 4 piezas) y alterna post estático."""
    recientes = database.list_content(limit=4) if database.DB_PATH.exists() else []
    videos_recientes = sum(1 for p in recientes[:3] if p.get("tipo") == "video")
    return "post" if videos_recientes >= 3 else "video"


def construir_contexto_creativo(*, tipo_forzado: str = "") -> str:
    formato = tipo_forzado if tipo_forzado in database.CONTENT_TIPOS else elegir_formato_sugerido()
    nichos_txt = sales_agent.cargar_todos_los_nichos_sin_precios() or "(usa enfoque universal para dueños de negocio)"
    resultados_txt = _leer_resultados_limpios()
    senales = database.list_recent_market_signals(limit=10) if database.DB_PATH.exists() else {"landing": [], "respuestas": []}
    ganchos_usados = database.list_recent_hooks(limit=35) if database.DB_PATH.exists() else []

    partes = [
        f"Formato requerido hoy: **{formato}**.",
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
            + "\n- ".join(ganchos_usados[:30])
        )
    partes.append(
        "Crea UNA pieza nueva que frene el scroll en el primer segundo, ataque un dolor real "
        "y termine llevando al prospecto a contar su problema en el link de la bio. "
        "Cero cifras, cero precios, cero humo."
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
        """Verifica llaves, cuota diaria de contenido y tope compartido de 0.50 USD."""
        if self.simulado:
            return ""
        if not self.conf["tiene_api_key"]:
            return "Falta ANTHROPIC_API_KEY en .env — el cerebro de contenido no llama a la API."
        creadas = database.content_created_today()
        if creadas >= int(self.conf["max_piezas"]):
            return f"Cuota diaria de contenido ya cumplida ({creadas}/{self.conf['max_piezas']})."
        gastado = self._gasto_hoy_usd()
        if gastado >= float(self.conf["max_usd"]):
            return (f"Tope diario compartido alcanzado ({gastado:.4f}/{self.conf['max_usd']:.2f} USD). "
                    "Vender va primero que publicar.")
        return ""

    def crear_pieza_del_dia(
        self, *, tipo_forzado: str = "", renderizar: bool = True, aprobar: bool = True,
    ) -> dict[str, object]:
        bloqueo = self.guardas_previas()
        if bloqueo:
            return {"ok": False, "creada": False, "motivo": bloqueo, "costo_usd": 0.0}

        system_prompt = construir_system_prompt_contenido()
        contexto = construir_contexto_creativo(tipo_forzado=tipo_forzado)

        if self.simulado:
            formato = tipo_forzado if tipo_forzado in database.CONTENT_TIPOS else elegir_formato_sugerido()
            return {
                "ok": True,
                "creada": False,
                "dry_run": True,
                "motivo": "dry_run_sin_api",
                "formato_sugerido": formato,
                "caracteres_prompt": len(system_prompt),
                "costo_usd": 0.0,
            }

        api_key = (self.cfg.get("ANTHROPIC_API_KEY") or "").strip()
        mensajes: list[dict] = [{"role": "user", "content": contexto}]
        ganchos_previos = {g.lower().strip() for g in database.list_recent_hooks(limit=50)}
        propuesta_valida: dict | None = None
        ultimo_error = "sin_propuesta"

        while self.turno < MAX_TURNOS_CONTENIDO:
            if self._gasto_hoy_usd() >= float(self.conf["max_usd"]):
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
            ok_pieza, detalle_o_limpia = self._validar_propuesta(datos, ganchos_previos)
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

        enc = content_manager.encolar(
            tipo=propuesta_valida["tipo"],
            gancho=propuesta_valida["gancho"],
            guion=propuesta_valida["guion"],
            caption=propuesta_valida["caption_completo"],
            nicho=propuesta_valida["nicho"],
            nota="creado por content_brain",
            escena=propuesta_valida["escena"],
            etiquetas=propuesta_valida["etiquetas"],
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

    def _validar_propuesta(self, datos: dict, ganchos_previos: set[str]) -> tuple[bool, dict | str]:
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

        cierre = " ".join(str(datos.get("cierre") or "Cuéntanos tu problema · link en bio").split()).strip()
        caption = str(datos.get("caption") or "").strip()
        nicho = " ".join(str(datos.get("nicho") or "general").split()).strip()[:60]

        try:
            escena = content_manager.normalizar_escena(str(datos.get("escena") or "contraste"))
            etiquetas = content_manager.normalizar_etiquetas(
                [str(x).replace("|", " ").replace(";", " ")[:content_manager.MAX_LARGO_ETIQUETA]
                 for x in (datos.get("etiquetas") or [])]
            )
        except ValueError as exc:
            return False, str(exc)

        guion = "\n".join(bloques) if tipo == "video" else ""
        motivos = sales_agent.revisar_guarda_precios(gancho, guion, cierre, caption, *etiquetas)
        if motivos:
            return False, "; ".join(motivos[:5])

        # Para video, `content_manager.generar()` usa `pieza['caption']` como línea de cierre
        # quemada si es corta, pero en Instagram queremos el caption largo: dejamos `cierre`
        # limpio en `caption` si no hay caption, o guardamos el caption completo para IG.
        caption_completo = caption or cierre
        return True, {
            "tipo": tipo,
            "nicho": nicho,
            "gancho": gancho,
            "guion": guion,
            "cierre": cierre,
            "caption_completo": caption_completo,
            "escena": escena,
            "etiquetas": etiquetas,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cerebro autónomo de contenido de El Socio.")
    parser.add_argument("--tipo", choices=["", "post", "video"], default="",
                        help="Forzar 'post' o 'video' (vacío = elige automático).")
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
    res = cerebro.crear_pieza_del_dia(
        tipo_forzado=args.tipo, renderizar=not args.sin_render,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
