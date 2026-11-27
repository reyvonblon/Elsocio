/**
 * Lienzo de PIXEL ART isométrico.
 *
 * Por qué existe (propuesta de Raymond, 2026-11-27): el techo que frenó 4 intentos es que mi
 * dibujo vectorial no da la calidad — SVG son curvas, proporciones y volumen, y ahí fallo.
 * El pixel art no es dibujo: es una grilla de celdas de color. Eso es aritmética, no destreza.
 * Y a baja resolución "tosco" ES el estilo, no un defecto: nadie mira un sprite de 24x44 y dice
 * que está mal dibujado. Es la salida del valle donde cayó `Socio.tsx`.
 *
 * Reparto de trabajo, deliberado:
 *  - Todo lo que es CAJA (pisos, paredes, escritorios, repisas, monitores) se calcula con
 *    geometría isométrica exacta: imposible que salga torcido.
 *  - Solo lo ORGÁNICO (el personaje, las plantas) se escribe como sprite de texto, celda por celda.
 *
 * Proyección: rombo 2:1 (ancho = 2 x alto), el estándar isométrico de los juegos de los 2000s.
 */

export type Rejilla = (string | null)[][];

export const rejilla = (ancho: number, alto: number): Rejilla =>
  Array.from({ length: alto }, () => new Array<string | null>(ancho).fill(null));

export const pintar = (g: Rejilla, x: number, y: number, color: string | null): void => {
  if (color === null) return;
  const px = Math.round(x);
  const py = Math.round(y);
  if (py < 0 || py >= g.length) return;
  if (px < 0 || px >= g[0].length) return;
  g[py][px] = color;
};

export const caja = (g: Rejilla, x: number, y: number, w: number, h: number, color: string): void => {
  for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) pintar(g, x + i, y + j, color);
};

/** Relleno de polígono por líneas de barrido: cualquier cuadrilátero sale con el borde exacto. */
export const poligono = (g: Rejilla, pts: [number, number][], color: string): void => {
  if (pts.length < 3) return;
  const ys = pts.map((p) => p[1]);
  const y0 = Math.floor(Math.min(...ys));
  const y1 = Math.ceil(Math.max(...ys));
  for (let y = y0; y <= y1; y++) {
    const yc = y + 0.5;
    const cortes: number[] = [];
    for (let k = 0; k < pts.length; k++) {
      const [ax, ay] = pts[k];
      const [bx, by] = pts[(k + 1) % pts.length];
      if ((ay <= yc && by > yc) || (by <= yc && ay > yc)) {
        cortes.push(ax + ((yc - ay) / (by - ay)) * (bx - ax));
      }
    }
    cortes.sort((a, b) => a - b);
    for (let k = 0; k + 1 < cortes.length; k += 2) {
      const xa = Math.round(cortes[k]);
      const xb = Math.round(cortes[k + 1]);
      for (let x = xa; x < xb; x++) pintar(g, x, y, color);
    }
  }
};

// ------------------------------------------------------------------ proyección isométrica

export type Camara = {
  /** Ancho del rombo de una baldosa (el alto es la mitad). */
  tw: number;
  /** Origen en pantalla del vértice superior de la baldosa (0,0). */
  ox: number;
  oy: number;
};

export const th = (c: Camara): number => c.tw / 2;

/** Pasa coordenada de mundo (i, j, altura z en píxeles) a pantalla. */
export const aPantalla = (c: Camara, i: number, j: number, z = 0): [number, number] => [
  c.ox + (i - j) * (c.tw / 2),
  c.oy + (i + j) * (th(c) / 2) - z,
];

/** Baldosa de piso con geometría exacta (sin costuras entre baldosas vecinas). */
export const baldosa = (g: Rejilla, c: Camara, i: number, j: number, color: string): void => {
  const [x, y] = aPantalla(c, i, j);
  poligono(
    g,
    [
      [x, y],
      [x + c.tw / 2, y + th(c) / 2],
      [x, y + th(c)],
      [x - c.tw / 2, y + th(c) / 2],
    ],
    color,
  );
};

export type Tonos = { top: string; izq: string; der: string };

/**
 * Caja isométrica: ocupa `wi` x `wj` baldosas desde (i, j), con altura `alto` en píxeles, y
 * su base levantada `base` píxeles del suelo. Tres caras con tres tonos = volumen real.
 */
export const cubo = (
  g: Rejilla,
  c: Camara,
  i: number,
  j: number,
  wi: number,
  wj: number,
  alto: number,
  t: Tonos,
  base = 0,
): void => {
  const zTop = base + alto;
  const P = (ii: number, jj: number, z: number) => aPantalla(c, ii, jj, z);
  // cara derecha (mira hacia abajo-derecha): el plano i = i+wi
  poligono(g, [P(i + wi, j, zTop), P(i + wi, j + wj, zTop), P(i + wi, j + wj, base), P(i + wi, j, base)], t.der);
  // cara izquierda (mira hacia abajo-izquierda): el plano j = j+wj
  poligono(g, [P(i, j + wj, zTop), P(i + wi, j + wj, zTop), P(i + wi, j + wj, base), P(i, j + wj, base)], t.izq);
  // tapa
  poligono(g, [P(i, j, zTop), P(i + wi, j, zTop), P(i + wi, j + wj, zTop), P(i, j + wj, zTop)], t.top);
};

// ------------------------------------------------------------------ sprites de texto

export type Sprite = { lineas: string[]; paleta: Record<string, string> };

/**
 * Estampa un sprite escrito como texto. `escala` entera: en pixel art ampliar es gratis y
 * estilísticamente correcto, así que un primer plano no cuesta dibujo nuevo (solo píxeles más
 * grandes). `ancla` es el punto de los pies, centrado en x.
 */
export const estampar = (
  g: Rejilla,
  sp: Sprite,
  piesX: number,
  piesY: number,
  escala = 1,
  espejo = false,
): void => {
  const h = sp.lineas.length;
  const w = Math.max(...sp.lineas.map((l) => l.length));
  const x0 = Math.round(piesX - (w * escala) / 2);
  const y0 = Math.round(piesY - h * escala);
  for (let fy = 0; fy < h; fy++) {
    const fila = sp.lineas[fy];
    for (let fx = 0; fx < w; fx++) {
      const ch = fila[espejo ? w - 1 - fx : fx] ?? ".";
      const color = sp.paleta[ch];
      if (!color) continue;
      for (let ey = 0; ey < escala; ey++)
        for (let ex = 0; ex < escala; ex++) pintar(g, x0 + fx * escala + ex, y0 + fy * escala + ey, color);
    }
  }
};

// ------------------------------------------------------------------ salida

export type Franja = { x: number; y: number; w: number; color: string };

/**
 * Comprime la rejilla a franjas horizontales del mismo color. Una rejilla de 135x240 son 32.400
 * celdas; comprimida baja a ~2.000 rectángulos, que es lo que hace viable animar esto a 30 fps.
 */
export const aFranjas = (g: Rejilla): Franja[] => {
  const out: Franja[] = [];
  for (let y = 0; y < g.length; y++) {
    let x = 0;
    const fila = g[y];
    while (x < fila.length) {
      const color = fila[x];
      if (color === null) {
        x++;
        continue;
      }
      let w = 1;
      while (x + w < fila.length && fila[x + w] === color) w++;
      out.push({ x, y, w, color });
      x += w;
    }
  }
  return out;
};
