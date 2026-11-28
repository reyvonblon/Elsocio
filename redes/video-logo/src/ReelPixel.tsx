import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { FUENTE } from "./comun";
import { aFranjas, caja, rejilla, type Camara, type Rejilla, type Sprite } from "./pixel/lienzo";
import { dibujarHabitacion, type Habitacion, type Mueble } from "./pixel/escena";
import { clienteAnimado, respiracion, socioAnimado, type Pose } from "./pixel/anim";
import { AZOTEA, OBRA, TALLER } from "./pixel/escenarios";
import { BOLSA, FICHA, PRENDA } from "./pixel/sprites";

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

/**
 * Densidad del pixel art. K=1 son 135x240 celdas lógicas; K=2 son 270x480, que es el doble de
 * detalle por objeto. Todo lo demás (baldosas, encuadres, escala de sprites) se multiplica por
 * K automáticamente, así que los planos se siguen escribiendo en la misma escala legible.
 */
const K = 2;
const LOGICO_W = 135 * K;
const LOGICO_H = 240 * K;
const FPS = 30;

// ---------------------------------------------------------------- tipos del guion

type Quien = "socio" | "cliente";

/**
 * Una llave es "en el segundo t, este actor está en esta baldosa haciendo esto". Entre llaves
 * se interpola. Esto es lo que faltaba: sin recorrido ni pose, los personajes eran estatuas y
 * el único cambio en pantalla venía de los cortes de plano.
 */
type Llave = {
  /** Segundo absoluto. Úsalo solo si el momento no depende de lo que se esté diciendo. */
  t?: number;
  /**
   * Momento expresado en FRASES (2 = al empezar la frase 3; 2.5 = a mitad de ella). Es lo que
   * hace que la acción siga sincronizada aunque la locución cambie de duración: los tiempos
   * reales se miden sobre el audio en cada render, y una frase más larga mueve la acción con
   * ella en vez de desencajarla.
   */
  f?: number;
  i: number;
  j: number;
  pose?: Pose;
};

type Actor = {
  quien: Quien;
  i?: number;
  j?: number;
  llaves?: Llave[];
  recolor?: Record<string, string>;
  espejo?: boolean;
  /** Desfase de la respiración: dos actores que respiran al mismo compás parecen autómatas. */
  desfase?: number;
};

/** Objeto de utilería que aparece, se mueve y desaparece: la bolsa, la prenda, la ficha. */
type Pieza = {
  sprite: Sprite;
  llaves?: Llave[];
  i?: number;
  j?: number;
  sube?: number;
  /** Ventana de existencia, en frases (mismo criterio que `Llave.f`). */
  desdeF?: number;
  hastaF?: number;
  sombra?: boolean;
};

/** Convierte un momento en frases a segundos sobre la línea de tiempo real del audio. */
const segundoDeFrase = (f: number, tramos: Tramo[]): number => {
  const k = Math.floor(f);
  if (k >= tramos.length) return tramos[tramos.length - 1].fin;
  const tr = tramos[Math.max(0, k)];
  return tr.inicio + (tr.fin - tr.inicio) * (f - k);
};

const resolverLlaves = (llaves: Llave[], tramos: Tramo[]): { t: number; i: number; j: number; pose: Pose }[] =>
  llaves.map((l) => ({
    t: l.f !== undefined ? segundoDeFrase(l.f, tramos) : (l.t ?? 0),
    i: l.i,
    j: l.j,
    pose: l.pose ?? "quieto",
  }));

/** Posición interpolada y pose vigente en el segundo `t`. */
const enTiempo = (llaves: { t: number; i: number; j: number; pose: Pose }[], t: number): { i: number; j: number; pose: Pose } => {
  if (t <= llaves[0].t) return llaves[0];
  for (let k = 0; k < llaves.length - 1; k++) {
    const a = llaves[k];
    const b = llaves[k + 1];
    if (t >= a.t && t < b.t) {
      const u = (t - a.t) / Math.max(0.01, b.t - a.t);
      return { i: a.i + (b.i - a.i) * u, j: a.j + (b.j - a.j) * u, pose: a.pose };
    }
  }
  return llaves[llaves.length - 1];
};

type Plano = {
  desde: Camara;
  hasta: Camara;
  /**
   * Multiplicador entero de los sprites en este plano. Es obligatorio moverlo con la baldosa:
   * la cámara acerca la GEOMETRÍA, pero un sprite mide lo que mide, así que sin esto un primer
   * plano agranda el cuarto y deja al personaje igual de pequeño. Va por plano y no por
   * fotograma a propósito: en pixel art solo se puede escalar por enteros, y hacerlo en medio
   * de un movimiento daría un salto visible.
   */
  escala?: number;
};

/**
 * Encuadre declarativo: "quiero que lo que está en la baldosa (ci,cj) tenga los pies en el
 * punto (sx,sy) de la pantalla, con este tamaño de baldosa". Calcular `ox`/`oy` a mano era
 * la fuente seguir de planos descuadrados.
 */
const encuadre = (twBase: number, ci: number, cj: number, sxBase: number, syBase: number, espejo?: boolean): Camara => {
  const tw = twBase * K;
  const sx = sxBase * K;
  const sy = syBase * K;
  return {
    tw,
    espejo,
    ox: sx - (ci - cj) * (tw / 2) * (espejo ? -1 : 1),
    oy: sy - (ci + cj) * (tw / 4) - tw / 8,
  };
};

type Frase = { texto: string; plano: number; voz?: Quien };

type Cielo = { bandas: string[]; skyline?: boolean };

export type Capitulo = {
  titulo: string;
  numero: number;
  badge: string;
  hab: Habitacion;
  cielo?: Cielo;
  actores: Actor[];
  /** Utilería con guion: lo que entra y sale de la escena mientras habla la voz. */
  piezas?: Pieza[];
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
    {
      quien: "cliente",
      recolor: { A: "#6b7f5e", a: "#53634a" },
      // entra por el frente cargando la bolsa, cruza el taller y la deja en la mesa
      llaves: [
        { f: 0, i: 6.7, j: 5.6, pose: "camina" },
        { f: 1, i: 5.8, j: 4.1, pose: "camina" },
        { f: 2, i: 5.2, j: 3.0, pose: "carga" },
        { f: 3.1, i: 4.6, j: 2.2, pose: "carga" },
        { f: 3.5, i: 4.6, j: 2.2, pose: "quieto" },
        { f: 9, i: 4.6, j: 2.2, pose: "quieto" },
      ],
    },
    {
      quien: "socio",
      desfase: 11,
      // mira la prenda, NIEGA con la cabeza, y al final se acerca a la mesa
      llaves: [
        { f: 0, i: 1.2, j: 2.8, pose: "quieto" },
        { f: 4, i: 1.2, j: 2.8, pose: "niega" },
        { f: 5, i: 1.2, j: 2.8, pose: "quieto" },
        { f: 6, i: 1.5, j: 3.3, pose: "camina" },
        { f: 6.5, i: 1.5, j: 3.3, pose: "quieto" },
        { f: 9, i: 1.5, j: 3.3, pose: "quieto" },
      ],
    },
  ],
  piezas: [
    // la bolsa viaja con el cliente y queda en el piso junto a la mesa
    {
      sprite: BOLSA,
      llaves: [
        { f: 0, i: 6.5, j: 5.3 },
        { f: 1, i: 5.6, j: 3.8 },
        { f: 2, i: 5.0, j: 2.7 },
        { f: 3.1, i: 4.4, j: 1.9 },
        { f: 3.4, i: 4.0, j: 2.6 },
        { f: 9, i: 4.0, j: 2.6 },
      ],
    },
    // la prenda mal cosida aparece sobre la mesa cuando la saca
    { sprite: PRENDA, i: 1.0, j: 0.9, sube: 14, desdeF: 3.15, hastaF: 5.0, sombra: false },
    // y la ficha técnica entra cuando la voz la nombra: es el objeto que resuelve el capítulo
    { sprite: FICHA, i: 1.0, j: 0.9, sube: 14, desdeF: 5.0, sombra: false },
  ],
  planos: [
    // entra al taller: general con acercamiento
    { desde: encuadre(16.5, 3.5, 3.5, 67, 146), hasta: encuadre(18.5, 3.5, 3.5, 67, 152), escala: 1 },
    // lo seguimos cruzar el cuarto
    { desde: encuadre(26, 5.6, 4.0, 78, 170), hasta: encuadre(29, 5.1, 2.9, 72, 176), escala: 1 },
    // primer plano del Socio
    { desde: encuadre(46, 1.7, 3.3, 62, 172), hasta: encuadre(52, 1.7, 3.3, 58, 180), escala: 2 },
    // la bolsa aterriza: plano medio de la mesa y los dos
    { desde: encuadre(29, 2.9, 2.5, 67, 172), hasta: encuadre(32, 2.9, 2.5, 62, 178), escala: 1 },
    // detalle de la prenda sobre la mesa, con el Socio negando al borde del cuadro
    { desde: encuadre(50, 1.5, 1.6, 72, 158), hasta: encuadre(56, 1.5, 1.6, 82, 166), escala: 2 },
    // entra la ficha
    { desde: encuadre(48, 1.4, 1.5, 70, 160), hasta: encuadre(53, 1.4, 1.5, 78, 168), escala: 2 },
    // cierre: el taller entero desde el OTRO lado
    { desde: encuadre(19, 3.5, 3.5, 67, 152, true), hasta: encuadre(16.5, 3.5, 3.5, 67, 146, true), escala: 1 },
  ],
  frases: [
    { texto: "Mandaste la muestra por WhatsApp.", plano: 0 },
    { texto: "Tres notas de voz y una foto borrosa.", plano: 1 },
    { texto: "El patronista no se equivocó. Lo que hizo fue adivinar.", plano: 2, voz: "socio" },
    { texto: "Y el lote salió dos centímetros corto.", plano: 3 },
    { texto: "Sesenta prendas. Otra vez.", plano: 4 },
    { texto: "Una ficha dice medidas, telas y costuras.", plano: 5, voz: "socio" },
    { texto: "El taller deja de adivinar.", plano: 6, voz: "socio" },
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
    {
      quien: "socio",
      desfase: 17,
      llaves: [
        { t: 0, i: 2.2, j: 4.8, pose: "camina" },
        { t: 9, i: 3.6, j: 4.8, pose: "camina" },
        { t: 30, i: 3.6, j: 4.8, pose: "quieto" },
      ],
    },
  ],
  planos: [
    // todo en espejo: este capítulo se ve desde el lado contrario al del taller
    { desde: encuadre(16.5, 4, 3.5, 67, 150, true), hasta: encuadre(18.5, 4, 3.5, 67, 156, true), escala: 1 },
    { desde: encuadre(44, 4.9, 3.9, 67, 170, true), hasta: encuadre(50, 4.9, 3.9, 67, 178, true), escala: 2 },
    // travelling lateral: la cámara cruza el apartamento vacío de lado a lado
    { desde: encuadre(29, 2.2, 2.6, 67, 164, true), hasta: encuadre(29, 5.8, 2.6, 67, 164, true), escala: 1 },
    { desde: encuadre(18, 4, 3.5, 67, 153, true), hasta: encuadre(15.5, 4, 3.5, 67, 146, true), escala: 1 },
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
    {
      quien: "socio",
      desfase: 13,
      llaves: [
        { t: 0, i: 2.2, j: 4.2, pose: "camina" },
        { t: 10, i: 3.8, j: 4.2, pose: "camina" },
        { t: 30, i: 3.8, j: 4.2, pose: "quieto" },
      ],
    },
  ],
  planos: [
    { desde: encuadre(15.5, 4, 4, 67, 150), hasta: encuadre(17.5, 4, 4, 67, 156), escala: 1 },
    { desde: encuadre(42, 3.9, 2.9, 67, 168), hasta: encuadre(48, 3.9, 2.9, 67, 176), escala: 2 },
    // travelling sobre las cajas sin fotografiar
    { desde: encuadre(28, 2.0, 1.2, 67, 158), hasta: encuadre(28, 6.0, 2.6, 67, 158), escala: 1 },
    { desde: encuadre(20, 4, 4, 67, 158), hasta: encuadre(17, 4, 4, 67, 150), escala: 1 },
  ],
  frases: [
    { texto: "Tienes cuarenta referencias listas.", plano: 0 },
    { texto: "Y una sola foto decente.", plano: 0 },
    { texto: "La del primer producto. De hace ocho meses.", plano: 1 },
    { texto: "El estudio no tiene cupo. El modelo cancela.", plano: 2 },
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

/**
 * Sin voz grabada se estima por número de palabras; con voz, `tiempos` trae la duración REAL
 * de cada frase medida sobre el audio, así el karaoke cae exacto sobre lo que se oye.
 */
const duracionFrase = (texto: string): number => {
  const palabras = texto.trim().split(/\s+/).length;
  return Math.min(3.4, Math.max(1.5, palabras * 0.34 + 0.45));
};

type Tramo = { inicio: number; fin: number; frase: Frase };

const linea = (cap: Capitulo, tiempos?: number[]): { tramos: Tramo[]; finFrases: number } => {
  const tramos: Tramo[] = [];
  let t = 0;
  cap.frases.forEach((frase, k) => {
    const d = tiempos?.[k] ?? duracionFrase(frase.texto);
    tramos.push({ inicio: t, fin: t + d, frase });
    t += d;
  });
  return { tramos, finFrases: t };
};

export const duracionCapitulo = (props: { capitulo?: string; tiempos?: number[] }): number => {
  const cap = CAPITULOS[props.capitulo ?? "taller"] ?? CAP_TALLER;
  return Math.round((linea(cap, props.tiempos).finFrases + CIERRE_SEG) * FPS);
};

const entre = (a: Camara, b: Camara, t: number): Camara => ({
  tw: a.tw + (b.tw - a.tw) * t,
  ox: a.ox + (b.ox - a.ox) * t,
  oy: a.oy + (b.oy - a.oy) * t,
  espejo: a.espejo,
});

// ---------------------------------------------------------------- pintado

const skyline = (g: Rejilla, yBase: number, desvio: number, k: number): void => {
  // silueta de ciudad: alturas fijas, para que no cambie entre fotogramas
  const torres = [6, 14, 9, 22, 11, 17, 7, 26, 12, 19, 8, 15, 23, 10, 18, 7, 13, 20];
  const ancho = 8 * k;
  torres.forEach((alto, idx) => {
    const h = alto * k;
    const x = Math.round(idx * ancho - 4 * k + desvio);
    caja(g, x, yBase - h, ancho - k, h, idx % 2 === 0 ? "#4a3a4a" : "#3f3242");
    if (alto > 12) caja(g, x + 2 * k, yBase - h + 3 * k, k, k, "#c98a55");
    if (alto > 18) caja(g, x + 4 * k, yBase - h + 7 * k, k, k, "#d6a165");
  });
};

const construir = (
  cap: Capitulo,
  cam: Camara,
  frame: number,
  seg: number,
  escala: number,
  tramos: Tramo[],
): Rejilla => {
  const g = rejilla(LOGICO_W, LOGICO_H);

  if (cap.cielo) {
    const altoBanda = Math.ceil((178 * K) / cap.cielo.bandas.length);
    cap.cielo.bandas.forEach((c, k) => caja(g, 0, k * altoBanda, LOGICO_W, altoBanda, c));
    // el horizonte vive donde empieza el piso, y se desplaza menos que la cámara (paralaje)
    if (cap.cielo.skyline) skyline(g, Math.round(cam.oy - 6 * K), (cam.ox - 67 * K) * 0.3, K);
  }

  // los actores entran como muebles-sprite, para que el pintor los ordene por profundidad
  const actores: Mueble[] = cap.actores.map((a) => {
    const pos = a.llaves ? enTiempo(resolverLlaves(a.llaves, tramos), seg) : { i: a.i ?? 0, j: a.j ?? 0, pose: "quieto" as Pose };
    const sprite =
      a.quien === "socio"
        ? socioAnimado({ habla: true, pose: pos.pose, frame })
        : clienteAnimado({ habla: true, pose: pos.pose, frame: frame + (a.desfase ?? 0) });
    return {
      tipo: "sprite",
      sprite,
      i: pos.i,
      j: pos.j,
      espejo: a.espejo,
      recolor: a.recolor,
      escala,
      sube: respiracion(frame, a.desfase ?? 0) * escala,
    };
  });

  // utilería con guion: solo existe dentro de su ventana de tiempo
  const piezas: Mueble[] = (cap.piezas ?? [])
    .filter(
      (p) =>
        seg >= (p.desdeF === undefined ? 0 : segundoDeFrase(p.desdeF, tramos)) &&
        seg < (p.hastaF === undefined ? 1e9 : segundoDeFrase(p.hastaF, tramos)),
    )
    .map((p) => {
      const pos = p.llaves ? enTiempo(resolverLlaves(p.llaves, tramos), seg) : { i: p.i ?? 0, j: p.j ?? 0 };
      return {
        tipo: "sprite" as const,
        sprite: p.sprite,
        i: pos.i,
        j: pos.j,
        escala,
        sube: (p.sube ?? 0) * escala,
        sombra: p.sombra,
      };
    });

  // la escenografía (perchas, matas, maniquí) crece con el plano igual que la gente
  const decorado = cap.hab.muebles.map((m) =>
    m.tipo === "sprite" ? { ...m, escala: (m.escala ?? 1) * escala, sube: (m.sube ?? 0) * escala } : m,
  );
  const hab: Habitacion = {
    ...cap.hab,
    altoPared: (cap.hab.altoPared ?? 46) * K,
    profundidadLosa: (cap.hab.profundidadLosa ?? 9) * K,
    muebles: [...decorado, ...piezas, ...actores],
  };
  dibujarHabitacion(g, cam, hab);
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

export const ReelPixel: React.FC<{ capitulo?: string; tiempos?: number[] }> = ({ capitulo = "taller", tiempos }) => {
  const frame = useCurrentFrame();
  const cap = CAPITULOS[capitulo] ?? CAP_TALLER;
  const { tramos, finFrases } = linea(cap, tiempos);
  const seg = frame / FPS;

  const actual = tramos.find((t) => seg >= t.inicio && seg < t.fin) ?? tramos[tramos.length - 1];
  const iPlano = actual.frase.plano;

  // el plano abarca de su primera a su última frase: la cámara recorre ESO, no cada frase
  const delPlano = tramos.filter((t) => t.frase.plano === iPlano);
  const p0 = delPlano[0].inicio;
  const p1 = delPlano[delPlano.length - 1].fin;
  const avancePlano = Math.max(0, Math.min(1, (seg - p0) / Math.max(0.1, p1 - p0)));
  const cam = entre(cap.planos[iPlano].desde, cap.planos[iPlano].hasta, avancePlano);

  const g = construir(cap, cam, frame, seg, (cap.planos[iPlano].escala ?? 1) * K, tramos);

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
      <AbsoluteFill style={{ opacity: enCierre ? 1 - cierreVisible * 0.93 : 1 }}>
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
            <div style={{ marginTop: 16, fontSize: 38, fontWeight: 800, color: "#d4697a", letterSpacing: "0.04em" }}>@elsociotuia</div>
          </div>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};
