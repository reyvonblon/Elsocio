import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { FUENTE } from "./comun";
import { aFranjas, caja, rejilla, type Camara, type Rejilla } from "./pixel/lienzo";
import { dibujarHabitacion, type Habitacion, type Mueble } from "./pixel/escena";
import { clienteAnimado, respiracion, socioAnimado } from "./pixel/anim";
import { AZOTEA, OBRA, TALLER } from "./pixel/escenarios";

/**
 * Reel en pixel art isométrico, en formato de CAPÍTULO.
 *
 * Tres reglas de la guía mandan aquí:
 *  - §15 regla 1: la cámara no se detiene jamás. Cada plano interpola de una cámara a otra; no
 *    existe el plano fijo.
 *  - §15 regla 2: un sujeto grande por plano. Se alterna general y primer plano; en pixel art
 *    acercarse es gratis (baldosa más grande + sprite a escala entera).
 *  - §15.1: el cuerpo entero se mueve siempre. Respiración y boca van a frecuencias distintas
 *    y desfasadas por actor.
 */

const LOGICO_W = 135;
const LOGICO_H = 240;
const FPS = 30;

// ---------------------------------------------------------------- tipos del guion

type Quien = "socio" | "cliente";

type Actor = {
  quien: Quien;
  i: number;
  j: number;
  /** Si está, el actor camina de (i,j) hasta aquí a lo largo del capítulo. */
  hasta?: [number, number];
  recolor?: Record<string, string>;
  espejo?: boolean;
  /** Desfase de la respiración: dos actores que respiran al mismo compás parecen autómatas. */
  desfase?: number;
};

type Plano = { desde: Camara; hasta: Camara };

/**
 * Encuadre declarativo: "quiero que lo que está en la baldosa (ci,cj) tenga los pies en el
 * punto (sx,sy) de la pantalla, con este tamaño de baldosa". Calcular `ox`/`oy` a mano era
 * la fuente seguir de planos descuadrados.
 */
const encuadre = (tw: number, ci: number, cj: number, sx: number, sy: number, espejo?: boolean): Camara => ({
  tw,
  espejo,
  ox: sx - (ci - cj) * (tw / 2) * (espejo ? -1 : 1),
  oy: sy - (ci + cj) * (tw / 4) - tw / 8,
});

type Frase = { texto: string; plano: number; voz?: Quien };

type Cielo = { bandas: string[]; skyline?: boolean };

export type Capitulo = {
  titulo: string;
  numero: number;
  badge: string;
  hab: Habitacion;
  cielo?: Cielo;
  actores: Actor[];
  planos: Plano[];
  frases: Frase[];
};

// ---------------------------------------------------------------- los tres capítulos

const ATARDECER: Cielo = {
  bandas: ["#2c2742", "#3a3050", "#4b3657", "#5f3d5a", "#76475a", "#8d5257", "#a56253", "#ba7450", "#c98a55", "#d6a165"],
  skyline: true,
};

/** Capítulo que SÍ cierra con El Socio. Nicho: fichas técnicas de ropa. */
const CAP_TALLER: Capitulo = {
  titulo: "El lote que volvió",
  numero: 3,
  badge: "CONFECCIÓN",
  hab: TALLER,
  actores: [
    { quien: "cliente", i: 4.6, j: 2.6, recolor: { A: "#6b7f5e", a: "#53634a", J: "#4a5668" } },
    { quien: "socio", i: 3.2, j: 3.8, desfase: 11 },
  ],
  planos: [
    // general: el cuarto entero como diorama, con un acercamiento lento
    { desde: encuadre(17.5, 3.5, 3.5, 67, 148), hasta: encuadre(19.5, 3.5, 3.5, 67, 153) },
    // primer plano del Socio
    { desde: encuadre(46, 3.7, 4.3, 67, 170), hasta: encuadre(53, 3.7, 4.3, 67, 177) },
    // detalle de la mesa de corte, con deriva hacia la derecha
    { desde: encuadre(36, 1.4, 2.2, 60, 150), hasta: encuadre(41, 1.4, 2.2, 68, 159) },
    // el mismo cuarto desde el OTRO lado, alejándose
    { desde: encuadre(19.5, 3.5, 3.5, 67, 153, true), hasta: encuadre(17.5, 3.5, 3.5, 67, 148, true) },
  ],
  frases: [
    { texto: "Mandaste la muestra por WhatsApp.", plano: 0 },
    { texto: "Tres notas de voz y una foto borrosa.", plano: 0 },
    { texto: "El patronista no se equivocó. Adivinó.", plano: 1, voz: "socio" },
    { texto: "Y el lote salió dos centímetros corto.", plano: 2 },
    { texto: "Sesenta prendas. Otra vez.", plano: 2 },
    { texto: "Una ficha dice medidas, telas y costuras.", plano: 3, voz: "socio" },
    { texto: "El taller deja de adivinar.", plano: 3, voz: "socio" },
  ],
};

/** Capítulo que NO vende: cierra en el dolor. Nicho: modelado 3D de espacios. */
const CAP_OBRA: Capitulo = {
  titulo: "El metro cuadrado invisible",
  numero: 11,
  badge: "ESPACIOS",
  hab: OBRA,
  actores: [
    { quien: "cliente", i: 4.0, j: 3.2, recolor: { A: "#8d5a4a", a: "#6e4538", H: "#4a3426" } },
    { quien: "cliente", i: 4.9, j: 3.6, recolor: { A: "#53637d", a: "#3f4d63" }, espejo: true, desfase: 7 },
    { quien: "socio", i: 2.2, j: 4.8, hasta: [3.6, 4.8], desfase: 17 },
  ],
  planos: [
    // todo en espejo: este capítulo se ve desde el lado contrario al del taller
    { desde: encuadre(16.5, 4, 3.5, 67, 150, true), hasta: encuadre(18.5, 4, 3.5, 67, 156, true) },
    { desde: encuadre(44, 4.9, 3.9, 67, 168, true), hasta: encuadre(50, 4.9, 3.9, 67, 175, true) },
    // travelling lateral: la cámara cruza el apartamento vacío de lado a lado
    { desde: encuadre(29, 2.2, 2.6, 67, 168, true), hasta: encuadre(29, 5.8, 2.6, 67, 168, true) },
    { desde: encuadre(18, 4, 3.5, 67, 153, true), hasta: encuadre(15.5, 4, 3.5, 67, 146, true) },
  ],
  frases: [
    { texto: "Te lo entregaron en obra gris.", plano: 0 },
    { texto: "El vendedor dijo: aquí le cabe de todo.", plano: 0 },
    { texto: "Y tú asientes, porque no te imaginas nada.", plano: 1 },
    { texto: "La cocina la decides el jueves.", plano: 2 },
    { texto: "Con un plano doblado y la plata ya puesta.", plano: 2 },
    { texto: "Suerte.", plano: 3, voz: "socio" },
  ],
};

/** Capítulo de absurdo, cierra en pregunta. Nicho: catálogo visual para e-commerce. */
const CAP_AZOTEA: Capitulo = {
  titulo: "El estudio que nunca llega",
  numero: 8,
  badge: "CATÁLOGO",
  hab: AZOTEA,
  cielo: ATARDECER,
  actores: [
    { quien: "cliente", i: 3.4, j: 2.4, recolor: { A: "#9c1c2e", a: "#78121f" } },
    { quien: "socio", i: 2.2, j: 4.2, hasta: [3.8, 4.2], desfase: 13 },
  ],
  planos: [
    { desde: encuadre(15.5, 4, 4, 67, 150), hasta: encuadre(17.5, 4, 4, 67, 156) },
    { desde: encuadre(42, 3.9, 2.9, 67, 164), hasta: encuadre(48, 3.9, 2.9, 67, 171) },
    // travelling sobre las cajas sin fotografiar
    { desde: encuadre(28, 2.0, 1.2, 67, 152), hasta: encuadre(28, 6.0, 2.6, 67, 152) },
    { desde: encuadre(20, 4, 4, 67, 158), hasta: encuadre(17, 4, 4, 67, 150) },
  ],
  frases: [
    { texto: "Tienes cuarenta referencias listas.", plano: 0 },
    { texto: "Y una sola foto decente.", plano: 0 },
    { texto: "La del primer producto. De hace ocho meses.", plano: 1 },
    { texto: "El estudio cuesta. El modelo cancela.", plano: 2 },
    { texto: "Entonces subes la del celular.", plano: 2 },
    { texto: "Sobre la mesa de la cocina.", plano: 3 },
    { texto: "Y te preguntas por qué nadie compra.", plano: 3, voz: "socio" },
  ],
};

export const CAPITULOS: Record<string, Capitulo> = {
  taller: CAP_TALLER,
  obra: CAP_OBRA,
  azotea: CAP_AZOTEA,
};

// ---------------------------------------------------------------- línea de tiempo

const CIERRE_SEG = 2.1;

const duracionFrase = (texto: string): number => {
  const palabras = texto.trim().split(/\s+/).length;
  return Math.min(3.4, Math.max(1.5, palabras * 0.34 + 0.45));
};

type Tramo = { inicio: number; fin: number; frase: Frase };

const linea = (cap: Capitulo): { tramos: Tramo[]; finFrases: number } => {
  const tramos: Tramo[] = [];
  let t = 0;
  for (const frase of cap.frases) {
    const d = duracionFrase(frase.texto);
    tramos.push({ inicio: t, fin: t + d, frase });
    t += d;
  }
  return { tramos, finFrases: t };
};

export const duracionCapitulo = (props: { capitulo?: string }): number => {
  const cap = CAPITULOS[props.capitulo ?? "taller"] ?? CAP_TALLER;
  return Math.round((linea(cap).finFrases + CIERRE_SEG) * FPS);
};

const entre = (a: Camara, b: Camara, t: number): Camara => ({
  tw: a.tw + (b.tw - a.tw) * t,
  ox: a.ox + (b.ox - a.ox) * t,
  oy: a.oy + (b.oy - a.oy) * t,
  espejo: a.espejo,
});

// ---------------------------------------------------------------- pintado

const skyline = (g: Rejilla, yBase: number, desvio: number): void => {
  // silueta de ciudad: alturas fijas, para que no cambie entre fotogramas
  const torres = [6, 14, 9, 22, 11, 17, 7, 26, 12, 19, 8, 15, 23, 10, 18, 7, 13, 20];
  const ancho = 8;
  torres.forEach((alto, k) => {
    const x = Math.round(k * ancho - 4 + desvio);
    caja(g, x, yBase - alto, ancho - 1, alto, k % 2 === 0 ? "#4a3a4a" : "#3f3242");
    if (alto > 12) caja(g, x + 2, yBase - alto + 3, 1, 1, "#c98a55");
    if (alto > 18) caja(g, x + 4, yBase - alto + 7, 1, 1, "#d6a165");
  });
};

const construir = (cap: Capitulo, cam: Camara, frame: number, avance: number): Rejilla => {
  const g = rejilla(LOGICO_W, LOGICO_H);

  if (cap.cielo) {
    const altoBanda = Math.ceil(178 / cap.cielo.bandas.length);
    cap.cielo.bandas.forEach((c, k) => caja(g, 0, k * altoBanda, LOGICO_W, altoBanda, c));
    // el horizonte vive donde empieza el piso, y se desplaza menos que la cámara (paralaje)
    if (cap.cielo.skyline) skyline(g, Math.round(cam.oy - 6), (cam.ox - 67) * 0.3);
  }

  // los actores entran como muebles-sprite, para que el pintor los ordene por profundidad
  const actores: Mueble[] = cap.actores.map((a) => {
    const camina = Boolean(a.hasta);
    const i = a.hasta ? a.i + (a.hasta[0] - a.i) * avance : a.i;
    const j = a.hasta ? a.j + (a.hasta[1] - a.j) * avance : a.j;
    const habla = true; // en los tres capítulos siempre hay alguien hablando en cuadro
    const sprite =
      a.quien === "socio"
        ? socioAnimado({ habla, camina, frame })
        : clienteAnimado({ habla, frame: frame + (a.desfase ?? 0) });
    return {
      tipo: "sprite",
      sprite,
      i,
      j,
      espejo: a.espejo,
      recolor: a.recolor,
      sube: respiracion(frame, a.desfase ?? 0),
    };
  });

  dibujarHabitacion(g, cam, { ...cap.hab, muebles: [...cap.hab.muebles, ...actores] });
  return g;
};

const Pixeles: React.FC<{ g: Rejilla }> = ({ g }) => {
  const franjas = aFranjas(g);
  return (
    <svg viewBox={`0 0 ${LOGICO_W} ${LOGICO_H}`} width="100%" height="100%" shapeRendering="crispEdges" style={{ display: "block" }}>
      {franjas.map((f, k) => (
        <rect key={k} x={f.x} y={f.y} width={f.w} height={1} fill={f.color} />
      ))}
    </svg>
  );
};

// ---------------------------------------------------------------- composición

export const ReelPixel: React.FC<{ capitulo?: string }> = ({ capitulo = "taller" }) => {
  const frame = useCurrentFrame();
  const cap = CAPITULOS[capitulo] ?? CAP_TALLER;
  const { tramos, finFrases } = linea(cap);
  const seg = frame / FPS;

  const actual = tramos.find((t) => seg >= t.inicio && seg < t.fin) ?? tramos[tramos.length - 1];
  const iPlano = actual.frase.plano;

  // el plano abarca de su primera a su última frase: la cámara recorre ESO, no cada frase
  const delPlano = tramos.filter((t) => t.frase.plano === iPlano);
  const p0 = delPlano[0].inicio;
  const p1 = delPlano[delPlano.length - 1].fin;
  const avancePlano = Math.max(0, Math.min(1, (seg - p0) / Math.max(0.1, p1 - p0)));
  const cam = entre(cap.planos[iPlano].desde, cap.planos[iPlano].hasta, avancePlano);

  const g = construir(cap, cam, frame, Math.min(1, seg / Math.max(0.1, finFrases)));

  // subtítulo palabra por palabra
  const palabras = actual.frase.texto.split(/\s+/);
  const dur = actual.fin - actual.inicio;
  const sonando = Math.floor(((seg - actual.inicio) / dur) * palabras.length);

  const enCierre = seg >= finFrases;
  const tituloVisible = interpolate(seg, [0, 0.4, 2.4, 3.0], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const cierreVisible = interpolate(frame, [finFrases * FPS, finFrases * FPS + 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: "#141017", fontFamily: FUENTE, overflow: "hidden" }}>
      <AbsoluteFill style={{ background: "radial-gradient(120% 70% at 50% 44%, #241c28 0%, #141017 74%)" }} />
      <AbsoluteFill style={{ opacity: enCierre ? 1 - cierreVisible * 0.82 : 1 }}>
        <Pixeles g={g} />
      </AbsoluteFill>

      {/* rótulo de capítulo: solo al principio, es lo que convierte el reel en serie */}
      <div style={{ position: "absolute", left: 0, right: 0, top: 150, textAlign: "center", opacity: tituloVisible }}>
        <div style={{ fontSize: 28, fontWeight: 800, letterSpacing: "0.42em", color: "#9c8f74" }}>
          CAPÍTULO {String(cap.numero).padStart(2, "0")}
        </div>
        <div style={{ marginTop: 16, fontSize: 60, fontWeight: 900, letterSpacing: "-0.02em", color: "#f3ead7" }}>{cap.titulo}</div>
      </div>

      {/* subtítulo karaoke */}
      {!enCierre && (
        <div
          style={{
            position: "absolute",
            left: 66,
            right: 66,
            bottom: 300,
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "center",
            gap: "10px 13px",
          }}
        >
          {palabras.map((p, k) => (
            <span
              key={k}
              style={{
                fontSize: 52,
                fontWeight: 900,
                color: k === sonando ? "#ffffff" : "rgba(243,234,215,0.72)",
                backgroundColor: k === sonando ? "#9c1c2e" : "transparent",
                padding: k === sonando ? "2px 13px" : "2px 0",
                textShadow: "0 3px 12px rgba(0,0,0,0.85)",
              }}
            >
              {p}
            </span>
          ))}
        </div>
      )}

      {/* cierre de marca */}
      {enCierre && (
        <AbsoluteFill style={{ display: "flex", alignItems: "center", justifyContent: "center", opacity: cierreVisible }}>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 26, fontWeight: 800, letterSpacing: "0.4em", color: "#9c8f74" }}>{cap.badge}</div>
            <div style={{ marginTop: 20, fontSize: 92, fontWeight: 900, letterSpacing: "-0.03em", color: "#f3ead7" }}>EL SOCIO</div>
            <div style={{ marginTop: 14, fontSize: 36, fontWeight: 700, color: "#9c1c2e" }}>@elsociotuia</div>
          </div>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};
