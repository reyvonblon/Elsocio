import React from "react";
import { interpolate } from "remotion";
import {
  Arbol,
  Banca,
  Bus,
  Caja,
  Carro,
  Cilindro,
  Farola,
  Linea,
  MUNDO,
  Persona,
  Pildora,
  Poly,
  RectX,
  RectY,
  RectZ,
  TextoPlanoY,
  iso,
  mezclar,
  tono,
} from "./base";
import { ANCHO_LOTE, FONDO_LOTE, INTERIORES, type EstadoLote, type NombreNicho } from "./interiores";

/**
 * La ciudad: UN solo mundo continuo donde viven los 4 nichos (como la cuadra de "Dos cafés").
 * Cada nicho tiene dos locales en la misma cuadra: A (sin sistema) y B (con El Socio),
 * separados por un edificio de relleno. La cámara viaja por este mundo: nunca se corta a negro.
 */

export const PASO_LOTE = 260;
export const ORDEN_NICHOS: NombreNicho[] = ["taller", "obra", "estudio", "oficina"];
const N_LOTES = 1 + ORDEN_NICHOS.length * 4;
export const ANCHO_MUNDO = N_LOTES * PASO_LOTE;

export type Lado = "A" | "B";

/** Índice de lote para cada nicho y lado: [F][A][F][B] por nicho. */
export const indiceLote = (nicho: NombreNicho, lado: Lado): number => 1 + ORDEN_NICHOS.indexOf(nicho) * 4 + (lado === "A" ? 0 : 2);
export const origenLote = (indice: number): [number, number] => [indice * PASO_LOTE, 0];

const ROTULO: Record<NombreNicho, string> = { taller: "TALLER", obra: "LOCAL", estudio: "TIENDA", oficina: "AGENCIA" };
export const NOMBRE_LOTE: Record<NombreNicho, string> = { taller: "Taller", obra: "Local", estudio: "Tienda", oficina: "Agencia" };

const hash = (n: number) => {
  const s = Math.sin(n * 127.1 + 311.7) * 43758.5453;
  return s - Math.floor(s);
};

// ------------------------------------------------------------------ edificios

const Ventanas: React.FC<{ x: number; y: number; w: number; d: number; z0: number; pisos: number; altoPiso: number; base: string; semilla: number }> = ({
  x, y, w, d, z0, pisos, altoPiso, base, semilla,
}) => {
  const out: React.ReactNode[] = [];
  const marco = mezclar(base, -0.25);
  const nx = Math.max(2, Math.floor(w / 30));
  const ny = Math.max(2, Math.floor(d / 30));
  for (let p = 0; p < pisos; p++) {
    const zb = z0 + p * altoPiso + altoPiso * 0.3;
    const zt = zb + altoPiso * 0.48;
    for (let i = 0; i < nx; i++) {
      const xx = x + ((i + 0.5) * w) / nx;
      const luz = hash(semilla + p * 13 + i) > 0.78;
      out.push(<RectY key={`l${p}-${i}`} Y={y + d + 0.4} x0={xx - 6} x1={xx + 6} z0={zb} z1={zt} f={luz ? "#f2e4bf" : MUNDO.vidrio} s={marco} sw={0.8} />);
    }
    for (let j = 0; j < ny; j++) {
      const yy = y + ((j + 0.5) * d) / ny;
      const luz = hash(semilla + p * 7 + j + 50) > 0.8;
      out.push(<RectX key={`r${p}-${j}`} X={x + w + 0.4} y0={yy - 6} y1={yy + 6} z0={zb} z1={zt} f={luz ? "#efe0b8" : mezclar(MUNDO.vidrio, -0.12)} s={marco} sw={0.8} />);
    }
  }
  return <g>{out}</g>;
};

const Edificio: React.FC<{
  x: number; y: number; w: number; d: number; pisos: number; color: string; semilla: number; local?: { rotulo: string; toldo: "vino" | "gris" } | null; o?: number;
}> = ({ x, y, w, d, pisos, color, semilla, local, o = 1 }) => {
  const altoPiso = 38;
  const baja = local ? 46 : 0;
  const h = baja + pisos * altoPiso;
  const c = tono(color);
  return (
    <g opacity={o}>
      <Caja x={x} y={y} w={w} d={d} h={h} c={c} sw={1.3} />
      <Ventanas x={x} y={y} w={w} d={d} z0={baja} pisos={pisos} altoPiso={altoPiso} base={color} semilla={semilla} />
      {/* Cornisa + techo */}
      <Caja x={x - 2} y={y - 2} z={h} w={w + 4} d={d + 4} h={4} c={tono(mezclar(color, -0.08))} sw={1} />
      {hash(semilla + 3) > 0.45 ? <Cilindro x={x + w * 0.3} y={y + d * 0.35} z={h + 4} r={9} h={16} c={tono("#e4dfd6")} /> : null}
      {hash(semilla + 5) > 0.4 ? <Caja x={x + w * 0.6} y={y + d * 0.5} z={h + 4} w={18} d={14} h={9} c={tono("#d6d2ca")} sw={0.8} /> : null}
      {local ? (
        <g>
          <RectY Y={y + d + 0.5} x0={x + 14} x1={x + w - 14} z0={2} z1={34} f={mezclar(MUNDO.vidrio, 0.2)} s={mezclar(color, -0.4)} sw={1.2} />
          <RectY Y={y + d + 0.7} x0={x + w * 0.42} x1={x + w * 0.58} z0={0} z1={32} f="#7a6a58" />
          <RectX X={x + w + 0.5} y0={y + 20} y1={y + d - 20} z0={8} z1={34} f={mezclar(MUNDO.vidrio, 0.1)} s={mezclar(color, -0.4)} sw={1} />
          {/* Toldo a rayas */}
          {Array.from({ length: 8 }).map((_, i) => {
            const x0 = x + 10 + ((w - 20) * i) / 8;
            const x1 = x + 10 + ((w - 20) * (i + 1)) / 8;
            const f = i % 2 === 0 ? (local.toldo === "vino" ? MUNDO.vino : "#7d7a74") : "#f3efe6";
            return <Poly key={i} p={[[x0, y + d, 42], [x1, y + d, 42], [x1, y + d + 18, 30], [x0, y + d + 18, 30]]} f={f} s="#5c5c5c" sw={0.5} />;
          })}
          <RectY Y={y + d + 0.6} x0={x + w * 0.25} x1={x + w * 0.75} z0={44.5} z1={56} f={MUNDO.tinta} />
          <TextoPlanoY x={x + w / 2} Y={y + d + 0.9} z={50.3} texto={local.rotulo} size={8} color="#ffffff" peso={900} espaciado={1.6} />
          {/* Mesitas en la acera */}
          <Cilindro x={x + 30} y={y + d + 24} r={5} h={12} c={tono("#e9e2d3")} />
          <Cilindro x={x + w - 34} y={y + d + 24} r={5} h={12} c={tono("#e9e2d3")} />
        </g>
      ) : null}
    </g>
  );
};

// ------------------------------------------------------------------ ciudad

export type EstadoMundo = {
  frame: number;
  fps: number;
  /** Cámara en coordenadas de mundo + zoom. */
  camX: number;
  camY: number;
  camZ: number;
  zoom: number;
  /** Lote donde está metida la cámara (se le quita el techo). -1 si ninguno. */
  loteFoco: number;
  /** Estado y frames-desde-cambio de cada lote especial. */
  estados: Record<number, { estado: EstadoLote; t: number }>;
  /** Lotes con píldora de nombre visible ("Taller A") y cuál va resaltado en vino. */
  pildoras: { indice: number; texto: string; resaltado: boolean }[];
  /** Lote que brilla (como "Café 2" iluminado). */
  brillo: number;
};

export const Ciudad: React.FC<EstadoMundo> = ({ frame, fps, camX, camY, camZ, zoom, loteFoco, estados, pildoras, brillo }) => {
  const [cx] = iso(camX, camY, camZ);
  // Margen de recorte: media pantalla en coordenadas de mundo + lo que mide el objeto más ancho
  // (un edificio de 200 ≈ 173 px en isométrico). Estaba en 420 y dibujaba edificios enteros, con sus
  // ventanas una por una, fuera de cámara en cada plano cerrado — el gasto grande del render.
  const visibleMedio = 1080 / 2 / zoom + 260;

  // Corte tipo maqueta: el techo del lote enfocado se desvanece al acercarse; los vecinos se vuelven fantasma.
  const opExterior = interpolate(zoom, [1.35, 1.75], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const opVecino = interpolate(zoom, [1.4, 1.9], [1, 0.18], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const visible = (x: number, y: number) => Math.abs(iso(x + 110, y + 100)[0] - cx) < visibleMedio;

  const filaFondo: React.ReactNode[] = [];
  const filaFrente: React.ReactNode[] = [];
  for (let i = -1; i <= N_LOTES; i++) {
    const [ox] = origenLote(i);
    // Fila de atrás (siempre relleno, más alta)
    const oyF = -250;
    if (visible(ox, oyF)) {
      const pisosF = 3 + Math.floor(hash(i + 40) * 4);
      filaFondo.push(
        <Edificio key={`f${i}`} x={ox + 10} y={oyF} w={200} d={200} pisos={pisosF} color={MUNDO.edificios[(i + 3 + 8) % 8]} semilla={i + 100} />,
      );
    }
    if (!visible(ox, 0)) continue;
    const nicho = ORDEN_NICHOS[Math.floor((i - 1) / 4)];
    const pos = (i - 1) % 4;
    const especial = i >= 1 && i < N_LOTES && (pos === 0 || pos === 2) && nicho;
    const esVecino = loteFoco >= 0 && Math.abs(i - loteFoco) === 1;
    if (especial) {
      const enFoco = i === loteFoco;
      const op = enFoco ? opExterior : esVecino ? opVecino : 1;
      const e = estados[i] ?? { estado: "caos" as EstadoLote, t: 999 };
      const Interior = INTERIORES[nicho];
      filaFrente.push(
        <g key={`e${i}`}>
          {op < 0.999 ? (
            <g transform={`translate(${iso(ox, 0)[0]} ${iso(ox, 0)[1]})`} opacity={enFoco ? 1 : 0}>
              <Interior estado={e.estado} t={e.t} frame={frame} fps={fps} />
            </g>
          ) : null}
          {op > 0.001 ? (
            <g>
              {brillo === i ? (
                <ellipse cx={iso(ox + 110, 210)[0]} cy={iso(ox + 110, 210)[1] - 40} rx={170} ry={95} fill="#f2d59a" opacity={0.35 + Math.sin(frame * 0.2) * 0.08} />
              ) : null}
              <Edificio
                x={ox}
                y={0}
                w={ANCHO_LOTE}
                d={FONDO_LOTE}
                pisos={2}
                color={pos === 2 ? "#f1e3c8" : "#e2ddd3"}
                semilla={i}
                local={{ rotulo: ROTULO[nicho], toldo: pos === 2 ? "vino" : "gris" }}
                o={op}
              />
            </g>
          ) : null}
        </g>,
      );
    } else {
      const pisos = 2 + Math.floor(hash(i) * 4);
      filaFrente.push(
        <Edificio
          key={`r${i}`}
          x={ox + 15}
          y={10}
          w={190}
          d={180}
          pisos={pisos}
          color={MUNDO.edificios[(i + 8) % 8]}
          semilla={i}
          local={null}
          o={esVecino ? opVecino : 1}
        />,
      );
    }
  }

  // Calle: carros y bus se mueven solos (vida de fondo)
  const carros = [0, 1, 2, 3, 4, 5, 6, 7].map((k) => {
    const sentido = k % 2 === 0 ? 1 : -1;
    const base = hash(k + 9) * ANCHO_MUNDO;
    const xx = ((((base + sentido * frame * (2.2 + hash(k) * 1.4)) % ANCHO_MUNDO) + ANCHO_MUNDO) % ANCHO_MUNDO) - 200;
    const yy = sentido === 1 ? 252 : 290;
    return { xx, yy, color: ["#e9e2d3", "#2f2f35", "#9c1c2e", "#c9c7c0", "#3f5163", "#d9a441", "#e9e2d3", "#5f7a5c"][k] };
  });
  const xBus = ((ANCHO_MUNDO * 0.4 - frame * 1.6) % ANCHO_MUNDO + ANCHO_MUNDO) % ANCHO_MUNDO - 200;

  const peatones = Array.from({ length: 18 }).map((_, k) => {
    const sentido = k % 2 === 0 ? 1 : -1;
    const acera = k % 3 === 0 ? 340 : 216;
    const base = hash(k + 77) * ANCHO_MUNDO;
    const xx = ((((base + sentido * frame * 0.55) % ANCHO_MUNDO) + ANCHO_MUNDO) % ANCHO_MUNDO) - 200;
    return { xx, yy: acera + (k % 2) * 8, semilla: k, paso: frame * 0.35 + k };
  });

  const mundoX0 = -400;
  const mundoX1 = ANCHO_MUNDO + 200;

  return (
    <g>
      {/* Suelo */}
      <RectZ x0={mundoX0} y0={-600} x1={mundoX1} y1={1100} f={MUNDO.plaza} />
      <RectZ x0={mundoX0} y0={-40} x1={mundoX1} y1={-10} f={MUNDO.acera} />
      <RectZ x0={mundoX0} y0={200} x1={mundoX1} y1={238} f={MUNDO.acera} s={mezclar(MUNDO.acera, -0.15)} sw={1} />
      <RectZ x0={mundoX0} y0={238} x1={mundoX1} y1={330} f={MUNDO.asfalto} />
      <RectZ x0={mundoX0} y0={330} x1={mundoX1} y1={362} f={MUNDO.acera} s={mezclar(MUNDO.acera, -0.15)} sw={1} />
      {Array.from({ length: Math.ceil((mundoX1 - mundoX0) / 60) }).map((_, i) => (
        <Linea key={`d${i}`} a={[mundoX0 + i * 60, 284, 0]} b={[mundoX0 + i * 60 + 30, 284, 0]} s={MUNDO.asfaltoLinea} sw={2} />
      ))}
      {/* Plaza: senderos en diagonal */}
      {Array.from({ length: Math.ceil((mundoX1 - mundoX0) / 520) }).map((_, i) => {
        const x0 = mundoX0 + i * 520;
        return (
          <g key={`p${i}`}>
            <Linea a={[x0, 380, 0]} b={[x0 + 360, 900, 0]} s="#e2e0d6" sw={7} />
            <Linea a={[x0 + 420, 380, 0]} b={[x0 + 120, 900, 0]} s="#e2e0d6" sw={7} />
            <Cilindro x={x0 + 250} y={600} r={22} h={6} c={tono("#d9d6cc")} />
            <Cilindro x={x0 + 250} y={600} z={6} r={6} h={14} c={tono("#c9d3d6")} />
          </g>
        );
      })}
      {filaFondo}
      {filaFrente}
      {/* Acera de enfrente: árboles y farolas */}
      {Array.from({ length: N_LOTES + 2 }).map((_, i) => {
        const xx = (i - 1) * PASO_LOTE + 130;
        if (Math.abs(iso(xx, 220)[0] - cx) > visibleMedio) return null;
        return (
          <g key={`a${i}`}>
            <Farola x={xx - 70} y={228} />
            {hash(i + 1) > 0.35 ? <Arbol x={xx + 40} y={228} r={13} /> : null}
          </g>
        );
      })}
      {carros.map((c, k) => (Math.abs(iso(c.xx, c.yy)[0] - cx) < visibleMedio ? <Carro key={`c${k}`} x={c.xx} y={c.yy} color={c.color} /> : null))}
      {Math.abs(iso(xBus, 290)[0] - cx) < visibleMedio ? <Bus x={xBus} y={292} /> : null}
      {peatones.map((p) =>
        Math.abs(iso(p.xx, p.yy)[0] - cx) < visibleMedio ? <Persona key={`pe${p.semilla}`} x={p.xx} y={p.yy} semilla={p.semilla} paso={p.paso} /> : null,
      )}
      {/* Plaza: árboles, bancas, gente quieta */}
      {Array.from({ length: Math.ceil((mundoX1 - mundoX0) / 90) }).map((_, i) => {
        const xx = mundoX0 + i * 90 + hash(i) * 40;
        const yy = 400 + hash(i + 3) * 420;
        if (Math.abs(iso(xx, yy)[0] - cx) > visibleMedio) return null;
        return (
          <g key={`t${i}`}>
            <Arbol x={xx} y={yy} r={12 + hash(i + 8) * 8} />
            {hash(i + 2) > 0.7 ? <Banca x={xx + 20} y={yy + 30} /> : null}
            {hash(i + 5) > 0.75 ? <Persona x={xx + 30} y={yy + 50} semilla={i} /> : null}
          </g>
        );
      })}
      {/* Píldoras "Taller A / Taller B" sobre los techos (tamaño constante en pantalla) */}
      {pildoras.map((p) => {
        const [ox] = origenLote(p.indice);
        const [sx, sy] = iso(ox + 110, 100, 150);
        return <Pildora key={`pl${p.indice}`} sx={sx} sy={sy} texto={p.texto} escala={1.05 / zoom} vino={p.resaltado} />;
      })}
    </g>
  );
};
