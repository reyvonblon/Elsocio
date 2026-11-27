/**
 * Una habitación es DATO, no código.
 *
 * Este es el punto que decide si la idea de Raymond escala: en el motor isométrico actual, un
 * escenario nuevo son ~120 líneas de SVG dibujadas a mano (y 50 escenarios, ~6.000 líneas que
 * además no pasan el filtro de calidad). Aquí un escenario nuevo es un objeto: cuántas baldosas,
 * de qué color, y una lista de cajas y sprites colocados en coordenadas de baldosa.
 * Escribir 50 escenarios se vuelve escribir 50 objetos, y la calidad no depende de mi pulso.
 */

import { aPantalla, baldosa, cubo, estampar, poligono, th, type Camara, type Rejilla, type Sprite, type Tonos } from "./lienzo";

export const MATERIALES: Record<string, Tonos> = {
  madera: { top: "#c9935f", izq: "#a5713f", der: "#7f5630" },
  maderaOscura: { top: "#8d6240", izq: "#6f4a2f", der: "#523621" },
  metal: { top: "#b9b5ac", izq: "#948f86", der: "#6e6a62" },
  blanco: { top: "#f1ece2", izq: "#d6d0c3", der: "#b4aea1" },
  vino: { top: "#b22337", izq: "#9c1c2e", der: "#68101d" },
  tinta: { top: "#2e2e38", izq: "#1d1d24", der: "#101014" },
  pantalla: { top: "#2e2e38", izq: "#9fb0bb", der: "#6f7d87" },
  carton: { top: "#d2a86f", izq: "#b08a55", der: "#86663c" },
  piedra: { top: "#cfcabd", izq: "#aaa59a", der: "#827e75" },
  pasto: { top: "#8fa273", izq: "#71835a", der: "#55643f" },
};

export type Mueble =
  | { tipo: "cubo"; i: number; j: number; wi: number; wj: number; alto: number; mat: keyof typeof MATERIALES; base?: number }
  | {
      tipo: "sprite";
      sprite: Sprite;
      i: number;
      j: number;
      escala?: number;
      espejo?: boolean;
      sube?: number;
      sombra?: boolean;
      /** Cambia entradas de la paleta: la misma persona con otra camisa es otra persona. */
      recolor?: Record<string, string>;
    }
  | { tipo: "tapete"; i: number; j: number; wi: number; wj: number; color: string };

export type Habitacion = {
  nombre: string;
  /** Baldosas a lo largo de cada eje. */
  ti: number;
  tj: number;
  pisoA: string;
  pisoB: string;
  /** Sin paredes = exterior (parque, calle, terraza). */
  exterior?: boolean;
  paredIzq?: string;
  paredDer?: string;
  altoPared?: number;
  /** Solo exteriores: grosor de la losa de tierra bajo el piso. */
  profundidadLosa?: number;
  ventanas?: { pared: "izq" | "der"; desde: number; hasta: number; z0: number; z1: number }[];
  muebles: Mueble[];
};

/** Mancha de sombra al pie de un sprite: sin esto los personajes flotan. */
const sombraPie = (g: Rejilla, x: number, y: number, c: Camara, color: string): void => {
  const w = c.tw * 0.34;
  const h = th(c) * 0.26;
  poligono(g, [[x, y - h], [x + w, y], [x, y + h], [x - w, y]], color);
};

export const dibujarHabitacion = (g: Rejilla, c: Camara, hab: Habitacion): void => {
  const altoPared = hab.altoPared ?? 46;
  const P = (i: number, j: number, z = 0) => aPantalla(c, i, j, z);

  // --- paredes primero: todo lo demás se dibuja encima (orden de pintura = profundidad)
  if (!hab.exterior) {
    const izq = hab.paredIzq ?? "#cdc1a6";
    const der = hab.paredDer ?? "#e3dac4";
    // pared de arriba-izquierda (plano i = 0)
    poligono(g, [P(0, 0, altoPared), P(0, hab.tj, altoPared), P(0, hab.tj, 0), P(0, 0, 0)], izq);
    // pared de arriba-derecha (plano j = 0)
    poligono(g, [P(0, 0, altoPared), P(hab.ti, 0, altoPared), P(hab.ti, 0, 0), P(0, 0, 0)], der);
    // canto superior: una línea clara arriba separa la pared del fondo oscuro
    poligono(g, [P(0, 0, altoPared), P(0, hab.tj, altoPared), P(0, hab.tj, altoPared - 2), P(0, 0, altoPared - 2)], "#f3ead7");
    poligono(g, [P(0, 0, altoPared), P(hab.ti, 0, altoPared), P(hab.ti, 0, altoPared - 2), P(0, 0, altoPared - 2)], "#fffaf0");
    // ventanas
    for (const v of hab.ventanas ?? []) {
      const marco = "#8d8578";
      const vidrio = "#bcd2dc";
      const luz = "#e4eef2";
      if (v.pared === "der") {
        poligono(g, [P(v.desde, 0, v.z1), P(v.hasta, 0, v.z1), P(v.hasta, 0, v.z0), P(v.desde, 0, v.z0)], marco);
        poligono(g, [P(v.desde + 0.12, 0, v.z1 - 2), P(v.hasta - 0.12, 0, v.z1 - 2), P(v.hasta - 0.12, 0, v.z0 + 2), P(v.desde + 0.12, 0, v.z0 + 2)], vidrio);
        const mitad = (v.desde + v.hasta) / 2;
        poligono(g, [P(v.desde + 0.12, 0, v.z1 - 2), P(mitad - 0.06, 0, v.z1 - 2), P(mitad - 0.06, 0, v.z0 + 2), P(v.desde + 0.12, 0, v.z0 + 2)], luz);
      } else {
        poligono(g, [P(0, v.desde, v.z1), P(0, v.hasta, v.z1), P(0, v.hasta, v.z0), P(0, v.desde, v.z0)], marco);
        poligono(g, [P(0, v.desde + 0.12, v.z1 - 2), P(0, v.hasta - 0.12, v.z1 - 2), P(0, v.hasta - 0.12, v.z0 + 2), P(0, v.desde + 0.12, v.z0 + 2)], vidrio);
      }
    }
    // zócalo
    poligono(g, [P(0, 0, 3), P(0, hab.tj, 3), P(0, hab.tj, 0), P(0, 0, 0)], "#a89c82");
    poligono(g, [P(0, 0, 3), P(hab.ti, 0, 3), P(hab.ti, 0, 0), P(0, 0, 0)], "#b9ad92");
  }

  // --- piso: base sólida primero (mata las costuras), damero encima
  if (hab.exterior) {
    // canto de tierra: convierte el recorte en una losa con volumen
    const prof = hab.profundidadLosa ?? 9;
    poligono(g, [P(hab.ti, 0), P(hab.ti, hab.tj), P(hab.ti, hab.tj, -prof), P(hab.ti, 0, -prof)], "#5b4733");
    poligono(g, [P(0, hab.tj), P(hab.ti, hab.tj), P(hab.ti, hab.tj, -prof), P(0, hab.tj, -prof)], "#6f5940");
  }
  poligono(g, [P(0, 0), P(hab.ti, 0), P(hab.ti, hab.tj), P(0, hab.tj)], hab.pisoA);
  for (let i = 0; i < hab.ti; i++) {
    for (let j = 0; j < hab.tj; j++) {
      if ((i + j) % 2 === 1) baldosa(g, c, i, j, hab.pisoB);
    }
  }

  // --- muebles, de atrás hacia adelante: lo que tiene i+j mayor se pinta después y tapa
  const orden = [...hab.muebles].sort((a, b) => a.i + a.j - (b.i + b.j));
  for (const m of orden) {
    if (m.tipo === "tapete") {
      poligono(g, [P(m.i, m.j), P(m.i + m.wi, m.j), P(m.i + m.wi, m.j + m.wj), P(m.i, m.j + m.wj)], m.color);
    } else if (m.tipo === "cubo") {
      cubo(g, c, m.i, m.j, m.wi, m.wj, m.alto, MATERIALES[m.mat], m.base ?? 0);
    } else {
      const [x, yBase] = aPantalla(c, m.i + 0.5, m.j + 0.5);
      const pies = yBase + th(c) * 0.25 - (m.sube ?? 0);
      if (m.sombra !== false) sombraPie(g, x, pies, c, oscurecer(hab.pisoA));
      const sp = m.recolor ? { lineas: m.sprite.lineas, paleta: { ...m.sprite.paleta, ...m.recolor } } : m.sprite;
      estampar(g, sp, x, pies, m.escala ?? 1, m.espejo);
    }
  }
};

/** Sombra sin canal alfa: se calcula un tono más oscuro del piso. */
export const oscurecer = (hex: string, cantidad = 0.22): string => {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g2 = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  const f = (v: number) => Math.max(0, Math.round(v * (1 - cantidad))).toString(16).padStart(2, "0");
  return `#${f(r)}${f(g2)}${f(b)}`;
};
