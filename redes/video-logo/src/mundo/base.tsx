import React from "react";

/**
 * Primitivas del mundo isométrico de El Socio (SVG puro, cero dependencias).
 *
 * Proyección isométrica 30°: x va hacia abajo-derecha, y hacia abajo-izquierda, z hacia arriba.
 * Todo lo que dibuja el mundo pasa por aquí, para que las piezas encajen entre sí.
 */

export const COS30 = 0.8660254037844387;

export const iso = (x: number, y: number, z = 0): [number, number] => [
  (x - y) * COS30,
  (x + y) * 0.5 - z,
];

export const pt = (x: number, y: number, z = 0): string => {
  const [sx, sy] = iso(x, y, z);
  return `${sx.toFixed(1)},${sy.toFixed(1)}`;
};

export type P3 = [number, number, number];

// ------------------------------------------------------------------ paleta del mundo

/** Paleta cálida y sobria: crema, piedra, madera y vino. Nada de cian ni neón. */
export const MUNDO = {
  vino: "#9c1c2e",
  vinoClaro: "#b22337",
  vinoOscuro: "#68101d",
  tinta: "#0a0a0a",
  crema: "#f5f0e6",
  blanco: "#ffffff",
  asfalto: "#b9b5ac",
  asfaltoLinea: "#e9e4d8",
  acera: "#dcd6c9",
  plaza: "#cfd1c3",
  pasto: "#bcc4ab",
  arbol: "#9aa58c",
  arbolLuz: "#b3bca4",
  tronco: "#7d7266",
  vidrio: "#9fb0bb",
  vidrioLuz: "#dfe7ea",
  madera: "#c9935f",
  maderaOscura: "#a5713f",
  concreto: "#bdb8ae",
  piel: ["#e0b48c", "#c58c63", "#8d5a3b", "#f0c9a5"],
  pelo: ["#2b2420", "#4a3426", "#151515", "#7a5a3a"],
  ropa: ["#3f5163", "#9c1c2e", "#d9a441", "#5f7a5c", "#6c5a7d", "#e9e2d3", "#2f2f35"],
  edificios: ["#efe6d4", "#e2d6bf", "#d8d8d3", "#e8d8bd", "#cfd3d8", "#f1ece2", "#dccbb5", "#c9c7c0"],
} as const;

// ------------------------------------------------------------------ color

const clamp255 = (v: number) => Math.max(0, Math.min(255, Math.round(v)));

export const mezclar = (hex: string, cantidad: number): string => {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  const destino = cantidad >= 0 ? 255 : 0;
  const a = Math.abs(cantidad);
  const out = [r, g, b].map((c) => clamp255(c + (destino - c) * a));
  return `#${out.map((c) => c.toString(16).padStart(2, "0")).join("")}`;
};

export type Tono3 = { t: string; l: string; r: string; s: string };

/** De un color base saca las 3 caras sombreadas + el trazo. */
export const tono = (base: string, trazo?: string): Tono3 => ({
  t: mezclar(base, 0.16),
  l: base,
  r: mezclar(base, -0.13),
  s: trazo ?? mezclar(base, -0.42),
});

// ------------------------------------------------------------------ polígonos y cajas

export const Poly: React.FC<{
  p: P3[];
  f: string;
  s?: string;
  sw?: number;
  o?: number;
}> = ({ p, f, s, sw = 1.3, o }) => (
  <polygon
    points={p.map(([x, y, z]) => pt(x, y, z)).join(" ")}
    fill={f}
    stroke={s ?? "none"}
    strokeWidth={sw}
    strokeLinejoin="round"
    opacity={o}
  />
);

/** Caja isométrica: cara y+d (izquierda), cara x+w (derecha) y techo. */
export const Caja: React.FC<{
  x: number;
  y: number;
  z?: number;
  w: number;
  d: number;
  h: number;
  c: Tono3;
  sw?: number;
  o?: number;
}> = ({ x, y, z = 0, w, d, h, c, sw = 1.2, o }) => (
  <g opacity={o}>
    <Poly p={[[x, y + d, z + h], [x + w, y + d, z + h], [x + w, y + d, z], [x, y + d, z]]} f={c.l} s={c.s} sw={sw} />
    <Poly p={[[x + w, y, z + h], [x + w, y + d, z + h], [x + w, y + d, z], [x + w, y, z]]} f={c.r} s={c.s} sw={sw} />
    <Poly p={[[x, y, z + h], [x + w, y, z + h], [x + w, y + d, z + h], [x, y + d, z + h]]} f={c.t} s={c.s} sw={sw} />
  </g>
);

/** Rectángulo sobre un plano y = Y (pared que corre a lo largo de x). */
export const RectY: React.FC<{ Y: number; x0: number; x1: number; z0: number; z1: number; f: string; s?: string; sw?: number; o?: number }> = ({
  Y, x0, x1, z0, z1, f, s, sw, o,
}) => <Poly p={[[x0, Y, z0], [x1, Y, z0], [x1, Y, z1], [x0, Y, z1]]} f={f} s={s} sw={sw} o={o} />;

/** Rectángulo sobre un plano x = X (pared que corre a lo largo de y). */
export const RectX: React.FC<{ X: number; y0: number; y1: number; z0: number; z1: number; f: string; s?: string; sw?: number; o?: number }> = ({
  X, y0, y1, z0, z1, f, s, sw, o,
}) => <Poly p={[[X, y0, z0], [X, y1, z0], [X, y1, z1], [X, y0, z1]]} f={f} s={s} sw={sw} o={o} />;

/** Rectángulo sobre el piso (plano z). */
export const RectZ: React.FC<{ z?: number; x0: number; y0: number; x1: number; y1: number; f: string; s?: string; sw?: number; o?: number }> = ({
  z = 0, x0, y0, x1, y1, f, s, sw, o,
}) => <Poly p={[[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]]} f={f} s={s} sw={sw} o={o} />;

/** Línea 3D. */
export const Linea: React.FC<{ a: P3; b: P3; s: string; sw?: number; dash?: string; o?: number }> = ({ a, b, s, sw = 1.5, dash, o }) => {
  const [x1, y1] = iso(...a);
  const [x2, y2] = iso(...b);
  return <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={s} strokeWidth={sw} strokeDasharray={dash} strokeLinecap="round" opacity={o} />;
};

/** Cilindro vertical (bobinas, macetas, baldes, columnas). */
export const Cilindro: React.FC<{ x: number; y: number; z?: number; r: number; h: number; c: Tono3; o?: number }> = ({
  x, y, z = 0, r, h, c, o,
}) => {
  const [cx, cy] = iso(x, y, z);
  const rx = r * 1.2247;
  const ry = r * 0.7071;
  return (
    <g opacity={o}>
      <path
        d={`M ${cx - rx} ${cy} L ${cx - rx} ${cy - h} A ${rx} ${ry} 0 0 0 ${cx + rx} ${cy - h} L ${cx + rx} ${cy} A ${rx} ${ry} 0 0 1 ${cx - rx} ${cy} Z`}
        fill={c.r}
        stroke={c.s}
        strokeWidth={1.1}
      />
      <ellipse cx={cx} cy={cy - h} rx={rx} ry={ry} fill={c.t} stroke={c.s} strokeWidth={1.1} />
    </g>
  );
};

/** Texto pegado a un plano y = const (fachada izquierda). */
export const TextoPlanoY: React.FC<{
  x: number; Y: number; z: number; texto: string; size: number; color: string; peso?: number; ancla?: "start" | "middle"; espaciado?: number;
}> = ({ x, Y, z, texto, size, color, peso = 800, ancla = "middle", espaciado = 1 }) => {
  const [sx, sy] = iso(x, Y, z);
  return (
    <text
      transform={`matrix(${COS30} 0.5 0 1 ${sx.toFixed(1)} ${sy.toFixed(1)})`}
      fontSize={size}
      fontWeight={peso}
      fill={color}
      textAnchor={ancla}
      dominantBaseline="central"
      letterSpacing={espaciado}
      fontFamily="-apple-system,BlinkMacSystemFont,'SF Pro Display',Helvetica,Arial,sans-serif"
    >
      {texto}
    </text>
  );
};

/** Texto pegado a un plano x = const (fachada derecha), leído de izquierda a derecha. */
export const TextoPlanoX: React.FC<{
  X: number; y: number; z: number; texto: string; size: number; color: string; peso?: number; espaciado?: number;
}> = ({ X, y, z, texto, size, color, peso = 800, espaciado = 1 }) => {
  const [sx, sy] = iso(X, y, z);
  return (
    <text
      transform={`matrix(${COS30} -0.5 0 1 ${sx.toFixed(1)} ${sy.toFixed(1)})`}
      fontSize={size}
      fontWeight={peso}
      fill={color}
      textAnchor="middle"
      dominantBaseline="central"
      letterSpacing={espaciado}
      fontFamily="-apple-system,BlinkMacSystemFont,'SF Pro Display',Helvetica,Arial,sans-serif"
    >
      {texto}
    </text>
  );
};

// ------------------------------------------------------------------ gente, árboles, calle

const elegir = <T,>(lista: readonly T[], semilla: number): T => lista[Math.abs(Math.floor(semilla)) % lista.length];

export const Persona: React.FC<{
  x: number; y: number; z?: number; semilla?: number; ropa?: string; sentada?: boolean; casco?: boolean; brazosArriba?: boolean; cabizbaja?: boolean; paso?: number;
}> = ({ x, y, z = 0, semilla = 0, ropa, sentada = false, casco = false, brazosArriba = false, cabizbaja = false, paso = 0 }) => {
  const piel = elegir(MUNDO.piel, semilla);
  const pelo = elegir(MUNDO.pelo, semilla + 1);
  const color = ropa ?? elegir(MUNDO.ropa, semilla + 2);
  const altPiernas = sentada ? 7 : 15;
  const zt = z + altPiernas;
  const [hx, hy] = iso(x, y, zt + 26);
  const balanceo = Math.sin(paso) * 2.2;
  return (
    <g>
      <ellipse cx={iso(x, y, z)[0]} cy={iso(x, y, z)[1] + 1} rx={9} ry={4.5} fill="rgba(40,30,20,0.18)" />
      {sentada ? (
        <Caja x={x - 4} y={y - 3} z={z} w={9} d={12} h={altPiernas} c={tono("#3a3a44")} sw={0.8} />
      ) : (
        <>
          <Caja x={x - 4} y={y - 3 + balanceo} z={z} w={4} d={5} h={altPiernas} c={tono("#34343d")} sw={0.8} />
          <Caja x={x} y={y - 3 - balanceo} z={z} w={4} d={5} h={altPiernas} c={tono("#34343d")} sw={0.8} />
        </>
      )}
      <Caja x={x - 5} y={y - 4} z={zt} w={10} d={8} h={19} c={tono(color)} sw={0.9} />
      {brazosArriba ? (
        <>
          <Linea a={[x - 5, y + 2, zt + 17]} b={[x - 9, y + 4, zt + 31]} s={piel} sw={3.4} />
          <Linea a={[x + 5, y - 2, zt + 17]} b={[x + 9, y - 4, zt + 31]} s={piel} sw={3.4} />
        </>
      ) : null}
      <circle cx={hx} cy={hy + (cabizbaja ? 3 : 0)} r={7.2} fill={piel} stroke={mezclar(piel, -0.4)} strokeWidth={0.9} />
      <path
        d={`M ${hx - 7.2} ${hy - 1 + (cabizbaja ? 3 : 0)} A 7.2 7.2 0 0 1 ${hx + 7.2} ${hy - 1 + (cabizbaja ? 3 : 0)} Q ${hx} ${hy - 4} ${hx - 7.2} ${hy - 1 + (cabizbaja ? 3 : 0)} Z`}
        fill={pelo}
      />
      {casco ? <ellipse cx={hx} cy={hy - 4} rx={8.6} ry={5} fill="#d9a441" stroke="#8a6420" strokeWidth={1} /> : null}
    </g>
  );
};

export const Arbol: React.FC<{ x: number; y: number; r?: number }> = ({ x, y, r = 15 }) => {
  const [cx, cy] = iso(x, y, 36);
  return (
    <g>
      <ellipse cx={iso(x, y)[0]} cy={iso(x, y)[1] + 2} rx={r * 1.1} ry={r * 0.5} fill="rgba(40,40,30,0.15)" />
      <Caja x={x - 2} y={y - 2} w={4} d={4} h={28} c={tono(MUNDO.tronco)} sw={0.6} />
      <circle cx={cx} cy={cy} r={r} fill={MUNDO.arbol} stroke={mezclar(MUNDO.arbol, -0.3)} strokeWidth={1} />
      <circle cx={cx - r * 0.3} cy={cy - r * 0.35} r={r * 0.45} fill={MUNDO.arbolLuz} />
    </g>
  );
};

export const Farola: React.FC<{ x: number; y: number }> = ({ x, y }) => {
  const [bx, by] = iso(x, y, 0);
  const [tx, ty] = iso(x, y, 58);
  return (
    <g>
      <line x1={bx} y1={by} x2={tx} y2={ty} stroke="#6d6a64" strokeWidth={2.4} />
      <circle cx={tx} cy={ty} r={4} fill="#f3e7c6" stroke="#6d6a64" strokeWidth={1} />
    </g>
  );
};

export const Banca: React.FC<{ x: number; y: number }> = ({ x, y }) => (
  <g>
    <Caja x={x} y={y} w={22} d={7} h={7} c={tono("#a98c6c")} sw={0.7} />
    <Caja x={x} y={y} z={7} w={22} d={2} h={8} c={tono("#a98c6c")} sw={0.7} />
  </g>
);

export const Carro: React.FC<{ x: number; y: number; color?: string; largo?: number }> = ({ x, y, color = "#e9e2d3", largo = 46 }) => (
  <g>
    <ellipse cx={iso(x + largo / 2, y + 11)[0]} cy={iso(x + largo / 2, y + 11)[1] + 2} rx={largo * 0.62} ry={12} fill="rgba(30,30,30,0.16)" />
    <Caja x={x} y={y} z={4} w={largo} d={22} h={12} c={tono(color)} sw={1} />
    <Caja x={x + largo * 0.22} y={y + 2} z={16} w={largo * 0.5} d={18} h={10} c={tono(mezclar(color, -0.05))} sw={1} />
    <RectY Y={y + 20} x0={x + largo * 0.25} x1={x + largo * 0.69} z0={18} z1={24.5} f="#7d8c96" />
    <circle cx={iso(x + 9, y + 22, 4)[0]} cy={iso(x + 9, y + 22, 4)[1]} r={4} fill="#2d2d2d" />
    <circle cx={iso(x + largo - 9, y + 22, 4)[0]} cy={iso(x + largo - 9, y + 22, 4)[1]} r={4} fill="#2d2d2d" />
  </g>
);

/** Bus/tranvía largo, como el de la referencia. */
export const Bus: React.FC<{ x: number; y: number }> = ({ x, y }) => (
  <g>
    <Caja x={x} y={y} z={4} w={120} d={26} h={30} c={tono("#ece6da")} sw={1.1} />
    {[0, 1, 2, 3, 4].map((i) => (
      <RectY key={i} Y={y + 26} x0={x + 8 + i * 22} x1={x + 24 + i * 22} z0={16} z1={29} f="#7d8c96" s="#5d5d5d" sw={0.6} />
    ))}
    <RectY Y={y + 26} x0={x} x1={x + 120} z0={8} z1={11} f={MUNDO.vino} />
  </g>
);

/** Píldora negra tipo "Café 1" sobre un punto del mundo (se dibuja dentro del grupo de cámara). */
export const Pildora: React.FC<{ sx: number; sy: number; texto: string; escala?: number; vino?: boolean }> = ({
  sx, sy, texto, escala = 1, vino = false,
}) => {
  const size = 19 * escala;
  const ancho = texto.length * size * 0.6 + 30 * escala;
  const alto = size + 18 * escala;
  return (
    <g transform={`translate(${sx} ${sy})`}>
      <path d={`M ${-7 * escala} ${alto / 2 - 1} L 0 ${alto / 2 + 9 * escala} L ${7 * escala} ${alto / 2 - 1} Z`} fill={vino ? MUNDO.vino : MUNDO.tinta} />
      <rect x={-ancho / 2} y={-alto / 2} width={ancho} height={alto} rx={alto / 2} fill={vino ? MUNDO.vino : MUNDO.tinta} />
      <text
        x={0}
        y={1}
        fontSize={size}
        fontWeight={800}
        fill={MUNDO.blanco}
        textAnchor="middle"
        dominantBaseline="central"
        fontFamily="-apple-system,BlinkMacSystemFont,'SF Pro Display',Helvetica,Arial,sans-serif"
      >
        {texto}
      </text>
    </g>
  );
};
