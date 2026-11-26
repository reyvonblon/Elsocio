import React from "react";
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { MUNDO, iso } from "./mundo/base";
import { ANCLAS, type EstadoLote, type NombreNicho } from "./mundo/interiores";
import { Ciudad, indiceLote, origenLote } from "./mundo/ciudad";
import {
  BADGE_NICHO, FUENTE, NOMBRE_LOTE, SAFE_BOTTOM, SAFE_TOP, TarjetaMarca, Titular,
  deducirNicho, duracionReel, ladoDe, normalizar, reelSchema, segmentosReel, type Lado, type PlanoEntrada, type PropsReel,
} from "./comun";
import { Tarjeta, type TipoTarjeta } from "./mundo/tarjetas";

/**
 * ReelMundo — Reel vertical 1080x1920 @ 30 fps, versión "mundo + cámara".
 *
 * Lo que aprendimos de la referencia "Dos cafés" (ver `contexto/guia-estilo-video.md` §6):
 *  1. UN mundo continuo (una cuadra con los dos locales). Nunca un fondo vacío.
 *  2. Una cámara que VIAJA: ciudad → calle → entra al local (el techo se desvanece) → detalle.
 *  3. CADA FRASE TIENE SU TOMA: la cámara muestra exactamente el sustantivo que dice la voz.
 *     Si la voz dice "taller", se ve un taller; si dice "pared", la cámara está en la pared.
 *  4. El dato va en un tooltip o en una tarjeta de UI encima de la escena, no en el locutor.
 *
 * Cada frase (gancho, bloques, cierre) es un "plano". El cerebro de contenido puede decir la toma
 * exacta de cada plano (`planos`); si no lo dice, `resolverPlanos` la deduce de las palabras de la
 * frase. Así la imagen nunca contradice la voz, aunque la IA se equivoque.
 */

export const NICHOS_MUNDO = ["taller", "obra", "estudio", "oficina"] as const;
export const TOMAS = ["ciudad", "pareja", "calle", "local", "detalle"] as const;
export type Toma = (typeof TOMAS)[number];

export const reelMundoSchema = reelSchema;
type Props = PropsReel;
export const duracionReelMundo = duracionReel;
export { deducirNicho };
const CENTRO_ESCENA_Y = 1150;




// ------------------------------------------------------------------ vocabulario: palabra → lugar

/** Palabra de la frase → punto exacto del local que la cámara debe mostrar. El orden importa: gana la primera. */
const FOCO_POR_PALABRA: Record<NombreNicho, [RegExp, string][]> = {
  taller: [
    [/ficha|medida|plano tecnico|especific/, "ficha"],
    [/audio|whatsapp|mensaje|foto borrosa|nota de voz/, "audios"],
    [/maquina|cose|costur|confecciona/, "maquinas"],
    [/corte|tela|molde|patron/, "mesa"],
    [/lote|devuel|entrega|llego|pedido/, "lote"],
    [/muestra|prenda|ajustado|talla|maniqui/, "maniqui"],
    [/coleccion|perchero|ropa/, "perchero"],
    [/adivina|interpreta|patronista|confund/, "persona"],
    [/idea|referencia|diseno/, "pared"],
  ],
  obra: [
    [/pared|romper|muro|demol/, "pared"],
    [/plano|medida|diseno|idea|referencia/, "plano"],
    [/render|ver antes|ves antes|terminad|listo|asi se ve|quedar/, "sala"],
    [/sala|mueble|sofa|decor/, "sofa"],
    [/obra|maestro|remodel|andamio|gast/, "andamio"],
    [/cable|electric|sorpresa|reproceso/, "cables"],
    [/luz|ventana/, "ventana"],
  ],
  estudio: [
    [/inventario|esperando|caja|bodega|sin foto/, "inventario"],
    [/catalogo|tienda online|publica|web|instagram/, "pantalla"],
    [/luz|estudio|profesional/, "luces"],
    [/celular|telefono|flash/, "celular"],
    [/foto|camara|sesion/, "camara"],
    [/producto|prenda|bolso|zapato/, "producto"],
    [/ropa|modelo/, "ropa"],
  ],
  oficina: [
    [/agenda|reunion|cita|calendario|agendad/, "agenda"],
    [/correo|email|bandeja|responde|mensaje|lead/, "pantalla"],
    [/llamada|telefono|whatsapp/, "telefono"],
    [/papel|excel|manual|olvid|seguimiento/, "papeles"],
    [/tiempo|cansad|solo|tu |dueno/, "persona"],
  ],
};

const TARJETA_POR_PALABRA: [RegExp, TipoTarjeta][] = [
  [/agenda|reunion|cita|calendario|agendad/, "agenda"],
  [/correo|email|bandeja|responde/, "correo"],
  [/ficha|medida exacta|plano tecnico/, "ficha"],
  [/catalogo|tienda online/, "catalogo"],
  [/render|ver antes|ves antes|asi se ve/, "render"],
  [/audio|whatsapp|nota de voz/, "chat"],
];


export type PlanoResuelto = {
  indice: number;
  tipo: "gancho" | "bloque" | "cierre";
  texto: string;
  inicio: number;
  fin: number;
  nicho: NombreNicho;
  lado: Lado;
  toma: Toma;
  foco: string;
  estado: EstadoLote;
  tooltip: string;
  tarjeta: TipoTarjeta | null;
  /** Último golpe del cierre: tarjeta de marca a pantalla completa. */
  final?: boolean;
};


export const deducirFoco = (nicho: NombreNicho, texto: string): string | null => {
  const t = normalizar(texto);
  for (const [re, foco] of FOCO_POR_PALABRA[nicho]) if (re.test(t)) return foco;
  return null;
};

export const resolverPlanos = (props: Props, duracionSeg: number): PlanoResuelto[] => {
  const { bloques = [], etiquetas = [], planos = [] } = props;
  const { nicho, segmentos } = segmentosReel(props, duracionSeg);
  const textos = segmentos;
  const inicios = segmentos.map((x) => x.inicio);

  let anterior: PlanoResuelto | null = null;
  let tooltipsUsados = 0;

  return textos.map((seg, i) => {
    const entrada: PlanoEntrada = planos[i] ?? {};
    const t = normalizar(seg.texto);

    // Lado A (sin sistema) o B (con El Socio)
    const lado: Lado = ladoDe(seg, bloques.length, entrada.lado);

    const focoPalabra = deducirFoco(nicho, seg.texto);
    const focoValido = (f?: string) => (f && ANCLAS[nicho][f] ? f : null);
    const foco = focoValido(entrada.foco) ?? focoPalabra ?? "centro";

    // Toma: el gancho abre en la ciudad, el cierre se aleja a la pareja de locales.
    let toma: Toma;
    if (entrada.toma) toma = entrada.toma;
    else if (seg.tipo === "gancho") toma = /\bdos\b|misma|mismo|ambos/.test(t) ? "ciudad" : "calle";
    // El cierre es de venta: "No seas el Taller A" tiene que mostrar el taller A por dentro (en caos)
    // y "Sé el Taller B" el mismo lugar resuelto. Desde la calle solo se veía un techo con una píldora.
    else if (seg.tipo === "cierre") toma = i === textos.length - 1 ? "pareja" : "local";
    else if (/\bdos\b|misma|mismo|ambos|solo uno|por que/.test(t)) toma = "pareja";
    else if (anterior && anterior.lado !== lado && anterior.toma === "detalle") toma = "local";
    else toma = foco !== "centro" ? "detalle" : "local";

    // Regla de variedad: dos planos seguidos nunca repiten encuadre.
    if (anterior && anterior.toma === toma && anterior.lado === lado && anterior.foco === foco) {
      const otros = Object.keys(ANCLAS[nicho]).filter((k) => k !== foco && k !== "centro");
      if (toma === "detalle") toma = "local";
      else if (otros.length) {
        toma = "detalle";
        return finalizar(otros[(i * 3) % otros.length]);
      }
    }
    return finalizar(foco);

    function finalizar(focoFinal: string): PlanoResuelto {
      const estado: EstadoLote = entrada.estado ?? (lado === "A" ? "caos" : "orden");
      let tarjeta: TipoTarjeta | null = entrada.tarjeta ?? null;
      if (!entrada.tarjeta && seg.tipo === "bloque") {
        for (const [re, tipo] of TARJETA_POR_PALABRA) {
          if (re.test(t)) {
            tarjeta = tipo;
            break;
          }
        }
        if (tarjeta === "chat" && lado === "B") tarjeta = null;
        if (tarjeta && tarjeta !== "chat" && lado === "A") tarjeta = null;
        if (anterior && anterior.tarjeta === tarjeta) tarjeta = null;
      }
      let tooltip = (entrada.tooltip || "").trim();
      if (!tooltip && seg.tipo === "bloque" && !tarjeta && (toma === "detalle" || toma === "local") && etiquetas.length && tooltipsUsados < 3) {
        tooltip = lado === "A" ? etiquetas[0] : etiquetas[Math.min(etiquetas.length - 1, 1 + tooltipsUsados)];
        tooltipsUsados++;
      }
      const r: PlanoResuelto = {
        indice: i,
        tipo: seg.tipo,
        texto: seg.texto,
        inicio: inicios[i],
        fin: i + 1 < textos.length ? inicios[i + 1] : duracionSeg,
        nicho,
        lado,
        toma,
        foco: focoFinal,
        estado,
        tooltip: tooltip.replace(/[0-9$%]/g, "").trim(),
        tarjeta: tarjeta === "ninguna" ? null : tarjeta,
        final: seg.tipo === "cierre" && i === textos.length - 1,
      };
      anterior = r;
      return r;
    }
  });
};

// ------------------------------------------------------------------ cámara

type Pose = { x: number; y: number; z: number; zoom: number; lote: number };

const poseDe = (p: PlanoResuelto): Pose => {
  const ia = indiceLote(p.nicho, "A");
  const ib = indiceLote(p.nicho, "B");
  const il = p.lado === "A" ? ia : ib;
  const [ox] = origenLote(il);
  const medio = (origenLote(ia)[0] + origenLote(ib)[0]) / 2 + 110;
  switch (p.toma) {
    // z alto = la cuadra baja en pantalla y deja de quedar pegada al titular; el zoom subió tras el
    // primer render real, donde los dos locales salían diminutos en el tercio de arriba.
    case "ciudad":
      return { x: medio, y: 160, z: 118, zoom: 0.9, lote: -1 };
    case "pareja":
      return { x: medio, y: 150, z: 120, zoom: 1.12, lote: -1 };
    case "calle":
      return { x: ox + 110, y: 170, z: 118, zoom: 1.4, lote: il };
    case "local":
      return { x: ox + 112, y: 108, z: 34, zoom: 2.05, lote: il };
    case "detalle":
    default: {
      const a = ANCLAS[p.nicho][p.foco] ?? ANCLAS[p.nicho].centro;
      return { x: ox + a[0], y: a[1] + 10, z: a[2] - 8, zoom: 3.3, lote: il };
    }
  }
};

const lerp = (a: number, b: number, k: number) => a + (b - a) * k;
const lerpLog = (a: number, b: number, k: number) => Math.exp(lerp(Math.log(a), Math.log(b), k));

const camaraEn = (planos: PlanoResuelto[], seg: number, fps: number): Pose & { activo: number } => {
  let i = 0;
  for (let k = 0; k < planos.length; k++) if (seg >= planos[k].inicio) i = k;
  const p = planos[i];
  const destino = poseDe(p);
  const dur = Math.max(0.6, p.fin - p.inicio);
  const tEn = seg - p.inicio;
  // Deriva lenta dentro del plano: la imagen nunca está quieta (guía §1: nada estático > 3 s).
  const deriva = interpolate(tEn, [0, dur], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const conDeriva = (q: Pose, k: number): Pose => ({ ...q, zoom: q.zoom * (1 + 0.07 * k), x: q.x + 6 * k, y: q.y - 4 * k });
  if (i === 0) {
    // Gancho: la cámara cae en picada sobre la cuadra en 0.7 s (golpe visual del primer segundo).
    const caida = interpolate(tEn, [0, 0.7], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.exp) });
    const fin = conDeriva(destino, deriva);
    return { ...fin, zoom: lerpLog(fin.zoom * 0.66, fin.zoom, caida), y: fin.y - 140 * (1 - caida), activo: i };
  }

  const origen = conDeriva(poseDe(planos[i - 1]), 1);
  const cambiaLote = origen.lote !== destino.lote && origen.lote >= 0 && destino.lote >= 0;
  // El viaje entre locales no puede comerse media frase: en el primer render real, "el otro recibe
  // una ficha" mostraba todavía el taller A durante un segundo largo.
  const trans = Math.min(cambiaLote ? 0.78 : 0.6, dur * 0.42);
  const k = interpolate(tEn, [0, trans], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic) });
  const fin = conDeriva(destino, deriva);
  let zoom: number;
  if (cambiaLote) {
    // Salto entre locales: la cámara se aleja a la calle y vuelve a entrar (como pasar de Café 1 a Café 2).
    const zMedio = 1.15;
    zoom = k < 0.5 ? lerpLog(origen.zoom, zMedio, k * 2) : lerpLog(zMedio, fin.zoom, (k - 0.5) * 2);
  } else {
    zoom = lerpLog(origen.zoom, fin.zoom, k);
  }
  const lote = k < 0.5 ? origen.lote : destino.lote;
  return { x: lerp(origen.x, fin.x, k), y: lerp(origen.y, fin.y, k), z: lerp(origen.z, fin.z, k), zoom, lote, activo: i };
};


// ------------------------------------------------------------------ tooltip sobre el mundo

const TooltipPantalla: React.FC<{ sx: number; sy: number; texto: string; frameLocal: number; fps: number; lado: Lado }> = ({ sx, sy, texto, frameLocal, fps, lado }) => {
  if (frameLocal < 0 || !texto) return null;
  const k = spring({ frame: frameLocal, fps, config: { damping: 14, mass: 0.6, stiffness: 200 } });
  const ancho = Math.max(220, texto.length * 19 + 92);
  const x = Math.max(70, Math.min(1080 - 170 - ancho, sx - ancho / 2));
  const y = Math.max(560, sy - 150);
  return (
    <div style={{ position: "absolute", left: 0, top: 0, width: 1080, height: 1920, pointerEvents: "none" }}>
      <svg width={1080} height={1920} style={{ position: "absolute", left: 0, top: 0 }}>
        <line x1={sx} y1={sy} x2={x + ancho / 2} y2={y + 70} stroke={MUNDO.tinta} strokeWidth={2.4} strokeDasharray="6 6" opacity={k} />
        <circle cx={sx} cy={sy} r={8 * k} fill={MUNDO.vino} stroke="#fff" strokeWidth={3} />
      </svg>
      <div
        style={{
          position: "absolute",
          left: x,
          top: y,
          width: ancho,
          height: 70,
          borderRadius: 18,
          backgroundColor: "#ffffff",
          boxShadow: "0 14px 34px rgba(10,10,10,0.22)",
          border: `2px solid ${lado === "B" ? MUNDO.vino : "#d8d2c6"}`,
          display: "flex",
          alignItems: "center",
          gap: 14,
          padding: "0 22px",
          transform: `translateY(${((1 - k) * 24).toFixed(1)}px) scale(${(0.85 + 0.15 * k).toFixed(3)})`,
          opacity: Math.min(1, k * 1.4),
          fontFamily: FUENTE,
        }}
      >
        <div
          style={{
            width: 34,
            height: 34,
            borderRadius: 17,
            backgroundColor: lado === "B" ? MUNDO.vino : "#2f2f35",
            color: "#fff",
            fontSize: 21,
            fontWeight: 900,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flex: "0 0 auto",
          }}
        >
          {lado === "B" ? "✓" : "!"}
        </div>
        <div style={{ fontSize: 30, fontWeight: 850, color: MUNDO.tinta, letterSpacing: "-0.01em", whiteSpace: "nowrap" }}>{texto}</div>
      </div>
    </div>
  );
};


// ------------------------------------------------------------------ componente


export const ReelMundo: React.FC<Props> = (props) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const seg = frame / fps;
  const planos = resolverPlanos(props, durationInFrames / fps);
  const cam = camaraEn(planos, seg, fps);
  const activo = planos[cam.activo];
  const nicho = activo.nicho;
  const ia = indiceLote(nicho, "A");
  const ib = indiceLote(nicho, "B");

  // Estado de cada local en el tiempo: cuando un plano entra a un local con otro estado, los objetos se rearman.
  const estados: Record<number, { estado: EstadoLote; t: number }> = {};
  [ia, ib].forEach((il) => {
    const eventos = planos.filter((p) => (p.lado === "A" ? ia : ib) === il && (p.toma === "local" || p.toma === "detalle"));
    if (!eventos.length) {
      estados[il] = { estado: il === ia ? "caos" : "orden", t: 999 };
      return;
    }
    // Último evento ya ocurrido (o el primero, si la cámara aún no ha entrado).
    let idx = 0;
    eventos.forEach((e, k) => {
      if (seg >= e.inicio) idx = k;
    });
    // Desde cuándo el local está en ese estado: inicio de la racha de eventos con el mismo estado.
    let desdeIdx = idx;
    while (desdeIdx > 0 && eventos[desdeIdx - 1].estado === eventos[idx].estado) desdeIdx--;
    const desde = eventos[desdeIdx].inicio;
    estados[il] = { estado: eventos[idx].estado, t: Math.max(0, frame - (desde * fps + 10)) };
  });

  const muestraPildoras = cam.zoom < 1.4;
  const pildoras = muestraPildoras
    ? [
        { indice: ia, texto: `${NOMBRE_LOTE[nicho]} A`, resaltado: false },
        { indice: ib, texto: `${NOMBRE_LOTE[nicho]} B`, resaltado: activo.lado === "B" && activo.tipo !== "gancho" },
      ]
    : [];
  const brillo = activo.lado === "B" && (activo.toma === "pareja" || activo.toma === "calle" || activo.toma === "ciudad") ? ib : -1;

  const [cx, cy] = iso(cam.x, cam.y, cam.z);
  const transformMundo = `translate(540 ${CENTRO_ESCENA_Y}) scale(${cam.zoom.toFixed(4)}) translate(${(-cx).toFixed(2)} ${(-cy).toFixed(2)})`;

  // Tooltip anclado al punto del mundo que nombra la frase.
  const loteActivo = activo.lado === "A" ? ia : ib;
  const ancla = ANCLAS[nicho][activo.foco] ?? ANCLAS[nicho].centro;
  const [axs, ays] = iso(origenLote(loteActivo)[0] + ancla[0], ancla[1], ancla[2]);
  const sx = (axs - cx) * cam.zoom + 540;
  const sy = (ays - cy) * cam.zoom + CENTRO_ESCENA_Y;
  const frameEnPlano = frame - Math.round(activo.inicio * fps);
  // Tooltip y tarjeta esperan a que la cámara aterrice (más si viene saltando de otro local).
  const previo = cam.activo > 0 ? planos[cam.activo - 1] : null;
  const saltaLote = previo !== null && previo.lado !== activo.lado && previo.toma !== "ciudad" && previo.toma !== "pareja";
  const espera = saltaLote ? 30 : 14;

  const badge = (props.badge || BADGE_NICHO[nicho]).replace(/[0-9$%]/g, "").toUpperCase().slice(0, 18);
  const progreso = frame / Math.max(1, durationInFrames - 1);

  return (
    <AbsoluteFill style={{ backgroundColor: MUNDO.plaza, fontFamily: FUENTE, overflow: "hidden" }}>
      <svg width={1080} height={1920} viewBox="0 0 1080 1920" style={{ position: "absolute", left: 0, top: 0 }}>
        <g transform={transformMundo}>
          <Ciudad
            frame={frame}
            fps={fps}
            camX={cam.x}
            camY={cam.y}
            camZ={cam.z}
            zoom={cam.zoom}
            loteFoco={cam.zoom > 1.3 ? cam.lote : -1}
            estados={estados}
            pildoras={pildoras}
            brillo={brillo}
          />
        </g>
      </svg>

      {/* Banda superior crema que se funde con la escena (como la referencia) */}
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: 1080,
          height: 700,
          background: `linear-gradient(to bottom, ${MUNDO.crema} 0%, ${MUNDO.crema} 58%, rgba(245,240,230,0.0) 100%)`,
        }}
      />

      {/* Cabecera: badge + marca */}
      <div style={{ position: "absolute", top: SAFE_TOP - 70, left: 76, right: 160, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 18px", borderRadius: 999, border: "1.5px solid rgba(10,10,10,0.16)", backgroundColor: "rgba(10,10,10,0.05)" }}>
          <span style={{ width: 11, height: 11, borderRadius: 6, backgroundColor: MUNDO.vino }} />
          <span style={{ fontSize: 21, fontWeight: 800, letterSpacing: "0.1em", color: MUNDO.tinta }}>{badge}</span>
        </div>
        <span style={{ fontFamily: "'Playfair Display', Georgia, serif", fontWeight: 800, fontSize: 26, color: MUNDO.tinta, opacity: 0.8 }}>El Socio</span>
      </div>

      {/* Titular: una frase por plano, entra palabra por palabra */}
      <div style={{ position: "absolute", top: SAFE_TOP + 20, left: 70, width: 1080 - 70 - 120 }}>
        {activo.final ? null : (
          <Titular
            key={activo.indice}
            texto={activo.texto}
            inicioFrame={Math.round(activo.inicio * fps)}
            finFrame={Math.round(activo.fin * fps)}
            frame={frame}
            fps={fps}
            inmediato={activo.tipo === "gancho"}
          />
        )}
      </div>

      {activo.tooltip && (activo.toma === "detalle" || activo.toma === "local") ? (
        <TooltipPantalla sx={sx} sy={sy} texto={activo.tooltip} frameLocal={frameEnPlano - espera} fps={fps} lado={activo.lado} />
      ) : null}

      {activo.tarjeta ? <Tarjeta tipo={activo.tarjeta} frameLocal={frameEnPlano - espera} fps={fps} nicho={nicho} /> : null}

      {activo.final ? <TarjetaMarca frameLocal={frameEnPlano} fps={fps} texto={activo.texto} /> : null}

      {/* Barra de ritmo */}
      <div style={{ display: activo.final ? "none" : "block", position: "absolute", left: 76, right: 160, bottom: SAFE_BOTTOM - 28, height: 6, borderRadius: 3, backgroundColor: "rgba(10,10,10,0.14)" }}>
        <div style={{ width: `${(progreso * 100).toFixed(1)}%`, height: "100%", borderRadius: 3, backgroundColor: MUNDO.vino }} />
      </div>
    </AbsoluteFill>
  );
};
