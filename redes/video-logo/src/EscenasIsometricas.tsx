import React from "react";
import { Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

/**
 * Escenas isométricas de El Socio v2. SVG geométrico puro, cero dependencias, 0 USD por render.
 *
 * Cumple `contexto/guia-estilo-video.md`:
 *  - Proyección isométrica real de 30° con sombreado de 3 caras y sombra proyectada en piso.
 *  - Bitemático real: se adapta a fondo oscuro (`#0a0a0a`) y a fondo crema (`#f5f0e6`).
 *  - Narrativa A vs B por fases (`fase`): la escena evoluciona plano a plano junto con la voz
 *    (lado A desordenado/problema -> transición/proceso -> lado B resuelto con tarjetas flotantes y sello).
 *  - CERO cifras: ni precios, ni plazos, ni porcentajes, ni números en etiquetas o tarjetas.
 */

export const PALETA = {
  tinta: "#0a0a0a",
  carbon: "#151517",
  carbonClaro: "#222228",
  blanco: "#ffffff",
  crema: "#f5f0e6",
  cremaMedia: "#e6dfd1",
  cremaSombra: "#cfc5b2",
  gris: "#6e6e73",
  grisClaro: "#9a9aa1",
  vino: "#9c1c2e",
  vinoClaro: "#b22337",
  vinoOscuro: "#68101d",
} as const;

export type TemaVisual = "oscuro" | "crema";

export const FUENTE_ESCENA =
  "-apple-system,BlinkMacSystemFont,'SF Pro Display','SF Pro Text','Segoe UI',Helvetica,Arial,sans-serif";

export const ANCHO_ESCENA = 940;
export const ALTO_ESCENA = 720;

export const NOMBRES_ESCENA = ["contraste", "flujo", "espacio3d", "agenda"] as const;
export type NombreEscena = (typeof NOMBRES_ESCENA)[number];

// ------------------------------------------------------------------ proyección isométrica 30°

const COS30 = 0.8660254037844387;

export const iso = (x: number, y: number, z = 0): [number, number] => [
  (x - y) * COS30,
  (x + y) * 0.5 - z,
];

const pt = (x: number, y: number, z = 0): string => {
  const [sx, sy] = iso(x, y, z);
  return `${sx.toFixed(2)},${sy.toFixed(2)}`;
};

const en = (x: number, y: number, z = 0): string => {
  const [sx, sy] = iso(x, y, z);
  return `translate(${sx.toFixed(2)} ${sy.toFixed(2)})`;
};

// ------------------------------------------------------------------ paleta adaptativa por tema

type Tono = "apagado" | "activo" | "vino" | "papel";

type ColoresCaja = {
  top: string;
  izq: string;
  der: string;
  borde: string;
  sombra: string;
};

const resolverColoresCaja = (tono: Tono, tema: TemaVisual): ColoresCaja => {
  const esCrema = tema === "crema";
  if (tono === "vino") {
    return {
      top: PALETA.vinoClaro,
      izq: PALETA.vino,
      der: PALETA.vinoOscuro,
      borde: esCrema ? PALETA.tinta : "#ffccd3",
      sombra: esCrema ? "rgba(10,10,10,0.16)" : "rgba(0,0,0,0.55)",
    };
  }
  if (tono === "papel") {
    return {
      top: esCrema ? PALETA.blanco : PALETA.crema,
      izq: PALETA.cremaMedia,
      der: PALETA.cremaSombra,
      borde: esCrema ? PALETA.tinta : PALETA.blanco,
      sombra: esCrema ? "rgba(10,10,10,0.12)" : "rgba(0,0,0,0.45)",
    };
  }
  if (tono === "activo") {
    return esCrema
      ? {
          top: PALETA.blanco,
          izq: "#ebe4d6",
          der: "#d5ccb9",
          borde: PALETA.tinta,
          sombra: "rgba(10,10,10,0.14)",
        }
      : {
          top: "#292930",
          izq: "#1b1b20",
          der: "#111115",
          borde: PALETA.blanco,
          sombra: "rgba(0,0,0,0.55)",
        };
  }
  return esCrema
    ? {
        top: "#e8e1d3",
        izq: "#d8d0c0",
        der: "#c4bba8",
        borde: "#6e6a61",
        sombra: "rgba(10,10,10,0.08)",
      }
    : {
        top: "#19191d",
        izq: "#121215",
        der: "#0c0c0e",
        borde: PALETA.gris,
        sombra: "rgba(0,0,0,0.4)",
      };
};

// ------------------------------------------------------------------ piezas reutilizables

type CajaProps = {
  w: number;
  d: number;
  h: number;
  tono?: Tono;
  tema?: TemaVisual;
  cara?: string;
  grosor?: number;
  opacidad?: number;
  conSombra?: boolean;
};

const Caja: React.FC<CajaProps> = ({
  w,
  d,
  h,
  tono = "apagado",
  tema = "oscuro",
  cara,
  grosor = 2.2,
  opacidad = 1,
  conSombra = false,
}) => {
  const col = resolverColoresCaja(tono, tema);
  return (
    <g opacity={opacidad}>
      {conSombra ? (
        <polygon
          points={`${pt(10, 14, 0)} ${pt(w + 14, 14, 0)} ${pt(w + 14, d + 18, 0)} ${pt(10, d + 18, 0)}`}
          fill={col.sombra}
        />
      ) : null}
      {/* Cara frontal-izquierda (y = d) */}
      <polygon
        points={`${pt(0, d, h)} ${pt(w, d, h)} ${pt(w, d, 0)} ${pt(0, d, 0)}`}
        fill={col.izq}
        stroke={col.borde}
        strokeWidth={grosor}
        strokeLinejoin="round"
      />
      {/* Cara frontal-derecha (x = w) */}
      <polygon
        points={`${pt(w, 0, h)} ${pt(w, d, h)} ${pt(w, d, 0)} ${pt(w, 0, 0)}`}
        fill={col.der}
        stroke={col.borde}
        strokeWidth={grosor}
        strokeLinejoin="round"
      />
      {/* Cara superior (z = h) */}
      <polygon
        points={`${pt(0, 0, h)} ${pt(w, 0, h)} ${pt(w, d, h)} ${pt(0, d, h)}`}
        fill={cara ?? col.top}
        stroke={col.borde}
        strokeWidth={grosor}
        strokeLinejoin="round"
      />
    </g>
  );
};

const Losa: React.FC<{
  w: number;
  d: number;
  h?: number;
  tono?: Tono;
  tema?: TemaVisual;
  cara?: string;
  opacidad?: number;
}> = ({ w, d, h = 11, tono = "apagado", tema = "oscuro", cara, opacidad = 1 }) => (
  <Caja w={w} d={d} h={h} tono={tono} tema={tema} cara={cara} grosor={1.7} opacidad={opacidad} />
);

/** Entrada con física `spring` limpia y sobria. */
const Aparece: React.FC<{
  entraEn: number;
  sube?: number;
  children: React.ReactNode;
}> = ({ entraEn, sube = 36, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const inicio = Math.round(entraEn * fps);
  if (frame < inicio) return null;
  const t = spring({ frame: frame - inicio, fps, config: { damping: 24, mass: 0.55, stiffness: 190 } });
  return (
    <g opacity={Math.min(1, t * 1.25)} transform={`translate(0 ${((1 - t) * sube).toFixed(2)})`}>
      {children}
    </g>
  );
};

/** Etiqueta flotante tipo tooltip con línea guía y punto de anclaje. */
const Tooltip: React.FC<{
  x: number;
  y: number;
  texto: string;
  entraEn: number;
  apuntaA?: [number, number];
  tono?: "neutro" | "vino";
  tema?: TemaVisual;
  tamano?: number;
}> = ({ x, y, texto, entraEn, apuntaA, tono = "neutro", tema = "oscuro", tamano = 21 }) => {
  const limpio = (texto || "").trim().toUpperCase();
  if (!limpio) return null;
  const espaciado = 1.6;
  const ancho = limpio.length * (tamano * 0.62 + espaciado) + 40;
  const alto = tamano + 22;
  const esVino = tono === "vino";
  const esCrema = tema === "crema";

  const relleno = esVino ? PALETA.vino : esCrema ? PALETA.tinta : PALETA.carbonClaro;
  const borde = esVino ? PALETA.vinoClaro : esCrema ? PALETA.tinta : PALETA.grisClaro;
  const colorLinea = esVino ? PALETA.vino : esCrema ? PALETA.tinta : PALETA.grisClaro;

  return (
    <Aparece entraEn={entraEn} sube={18}>
      {apuntaA ? (
        <g>
          <line
            x1={x}
            y1={y + alto / 2}
            x2={apuntaA[0]}
            y2={apuntaA[1]}
            stroke={colorLinea}
            strokeWidth={2}
            strokeDasharray="5 5"
          />
          <circle cx={apuntaA[0]} cy={apuntaA[1]} r={5} fill={colorLinea} />
        </g>
      ) : null}
      <rect
        x={x - ancho / 2}
        y={y - alto / 2 + 4}
        width={ancho}
        height={alto}
        rx={alto / 2}
        fill="rgba(0,0,0,0.22)"
      />
      <rect
        x={x - ancho / 2}
        y={y - alto / 2}
        width={ancho}
        height={alto}
        rx={alto / 2}
        fill={relleno}
        stroke={borde}
        strokeWidth={2}
      />
      <text
        x={x}
        y={y}
        fill={PALETA.blanco}
        fontSize={tamano}
        fontWeight={800}
        letterSpacing={espaciado}
        textAnchor="middle"
        dominantBaseline="central"
      >
        {limpio}
      </text>
    </Aparece>
  );
};

/** Tarjeta flotante estilo UI editorial (como las tarjetas de Coffeefy / dajent, sin cifras). */
const TarjetaUI: React.FC<{
  x: number;
  y: number;
  titulo: string;
  estadoTexto: string;
  entraEn: number;
  resuelta?: boolean;
  tema?: TemaVisual;
}> = ({ x, y, titulo, estadoTexto, entraEn, resuelta = true, tema = "oscuro" }) => {
  const ancho = 286;
  const alto = 104;
  const esCrema = tema === "crema";
  const fondo = esCrema ? PALETA.blanco : "#1b1b20";
  const borde = resuelta ? PALETA.vino : esCrema ? "#b8b0a0" : PALETA.gris;
  const colorTitulo = esCrema ? PALETA.tinta : PALETA.blanco;

  return (
    <Aparece entraEn={entraEn} sube={22}>
      <g transform={`translate(${x - ancho / 2} ${y - alto / 2})`}>
        <rect x={4} y={8} width={ancho} height={alto} rx={16} fill="rgba(0,0,0,0.22)" />
        <rect
          x={0}
          y={0}
          width={ancho}
          height={alto}
          rx={16}
          fill={fondo}
          stroke={borde}
          strokeWidth={2.4}
        />
        <circle cx={26} cy={32} r={8} fill={resuelta ? PALETA.vino : PALETA.gris} />
        <text
          x={46}
          y={32}
          fill={colorTitulo}
          fontSize={18}
          fontWeight={800}
          letterSpacing={1.1}
          dominantBaseline="central"
        >
          {titulo.toUpperCase()}
        </text>
        <rect
          x={18}
          y={54}
          width={ancho - 36}
          height={34}
          rx={9}
          fill={resuelta ? PALETA.vino : esCrema ? "#e6dfd1" : "#282830"}
        />
        <text
          x={ancho / 2}
          y={71}
          fill={resuelta ? PALETA.blanco : PALETA.gris}
          fontSize={16}
          fontWeight={800}
          letterSpacing={1.4}
          textAnchor="middle"
          dominantBaseline="central"
        >
          {estadoTexto.toUpperCase()}
        </text>
      </g>
    </Aparece>
  );
};

/** Sello estampado de cierre: entra con golpe seco y queda firme. */
const Sello: React.FC<{
  x: number;
  y: number;
  texto: string;
  entraEn: number;
  rotacion?: number;
  tamano?: number;
}> = ({ x, y, texto, entraEn, rotacion = -7, tamano = 28 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const limpio = (texto || "").trim().toUpperCase();
  const inicio = Math.round(entraEn * fps);
  if (!limpio || frame < inicio) return null;

  const t = spring({ frame: frame - inicio, fps, config: { damping: 14, mass: 0.8, stiffness: 220 } });
  const escala = interpolate(t, [0, 1], [1.65, 1]);
  const espaciado = 2.8;
  const ancho = limpio.length * (tamano * 0.66 + espaciado) + 46;
  const alto = tamano + 28;

  return (
    <g
      opacity={Math.min(1, t * 1.7)}
      transform={`translate(${x} ${y}) rotate(${rotacion}) scale(${escala.toFixed(3)})`}
    >
      <rect
        x={-ancho / 2}
        y={-alto / 2 + 5}
        width={ancho}
        height={alto}
        rx={10}
        fill="rgba(0,0,0,0.28)"
      />
      <rect
        x={-ancho / 2}
        y={-alto / 2}
        width={ancho}
        height={alto}
        rx={10}
        fill={PALETA.vino}
        stroke={PALETA.blanco}
        strokeWidth={2.8}
      />
      <rect
        x={-ancho / 2 + 7}
        y={-alto / 2 + 7}
        width={ancho - 14}
        height={alto - 14}
        rx={6}
        fill="none"
        stroke={PALETA.blanco}
        strokeWidth={1.5}
        opacity={0.55}
      />
      <text
        x={0}
        y={0}
        fill={PALETA.blanco}
        fontSize={tamano}
        fontWeight={900}
        letterSpacing={espaciado}
        textAnchor="middle"
        dominantBaseline="central"
      >
        {limpio}
      </text>
    </g>
  );
};

/** Conector isométrico con pulso luminoso viajero. */
const Conector: React.FC<{
  desde: [number, number];
  hasta: [number, number];
  entraEn: number;
  duracion?: number;
  color?: string;
  ancho?: number;
}> = ({ desde, hasta, entraEn, duracion = 0.48, color = PALETA.vinoClaro, ancho = 5.5 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const inicio = entraEn * fps;
  const avance = interpolate(frame, [inicio, inicio + duracion * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  if (avance <= 0) return null;

  const [x1, y1] = desde;
  const [x2, y2] = hasta;
  const px = x1 + (x2 - x1) * avance;
  const py = y1 + (y2 - y1) * avance;
  const largo = Math.hypot(x2 - x1, y2 - y1) || 1;
  const ux = (x2 - x1) / largo;
  const uy = (y2 - y1) / largo;
  const a = 17;
  const b = 9.5;

  // Pulso sutil que recorre la línea una vez conectada
  const ciclo = ((frame - inicio) / (fps * 1.4)) % 1;
  const pulsoX = x1 + (x2 - x1) * Math.max(0, ciclo);
  const pulsoY = y1 + (y2 - y1) * Math.max(0, ciclo);

  return (
    <g>
      <line
        x1={x1}
        y1={y1}
        x2={px}
        y2={py}
        stroke={color}
        strokeWidth={ancho}
        strokeLinecap="round"
      />
      {avance > 0.96 ? (
        <>
          <polygon
            points={[
              `${x2},${y2}`,
              `${x2 - ux * a - uy * b},${y2 - uy * a + ux * b}`,
              `${x2 - ux * a + uy * b},${y2 - uy * a - ux * b}`,
            ].join(" ")}
            fill={color}
          />
          <circle cx={pulsoX} cy={pulsoY} r={6} fill={PALETA.blanco} opacity={0.85} />
        </>
      ) : null}
    </g>
  );
};

const Check: React.FC<{ x: number; y: number; entraEn: number; tamano?: number }> = ({
  x,
  y,
  entraEn,
  tamano = 66,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const inicio = entraEn * fps;
  const avance = interpolate(frame, [inicio, inicio + 0.42 * fps], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  if (avance >= 1) return null;
  const s = tamano / 64;

  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <circle cy={4} r={31} fill="rgba(0,0,0,0.25)" />
      <circle r={30} fill={PALETA.vino} stroke={PALETA.blanco} strokeWidth={3} />
      <path
        d="M -14 1 L -4 12 L 15 -11"
        fill="none"
        stroke={PALETA.blanco}
        strokeWidth={6.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        pathLength={1}
        strokeDasharray={1}
        strokeDashoffset={avance}
      />
    </g>
  );
};

const MarcaAlerta: React.FC<{ x: number; y: number; entraEn: number; tema?: TemaVisual }> = ({
  x,
  y,
  entraEn,
  tema = "oscuro",
}) => {
  const esCrema = tema === "crema";
  return (
    <Aparece entraEn={entraEn} sube={14}>
      <g transform={`translate(${x} ${y})`}>
        <circle
          r={23}
          fill={esCrema ? "#ded6c6" : "#222228"}
          stroke={esCrema ? PALETA.tinta : PALETA.grisClaro}
          strokeWidth={2.5}
        />
        <line
          x1={-7}
          y1={-7}
          x2={7}
          y2={7}
          stroke={esCrema ? PALETA.tinta : PALETA.grisClaro}
          strokeWidth={3.5}
          strokeLinecap="round"
        />
        <line
          x1={7}
          y1={-7}
          x2={-7}
          y2={7}
          stroke={esCrema ? PALETA.tinta : PALETA.grisClaro}
          strokeWidth={3.5}
          strokeLinecap="round"
        />
      </g>
    </Aparece>
  );
};

const Rotulo: React.FC<{
  x: number;
  y: number;
  texto: string;
  entraEn: number;
  tema?: TemaVisual;
  destacado?: boolean;
}> = ({ x, y, texto, entraEn, tema = "oscuro", destacado = false }) => {
  const limpio = (texto || "").trim().toUpperCase();
  if (!limpio) return null;
  const color = destacado
    ? tema === "crema"
      ? PALETA.vino
      : PALETA.blanco
    : tema === "crema"
      ? "#5c574f"
      : PALETA.grisClaro;

  return (
    <Aparece entraEn={entraEn} sube={10}>
      <text
        x={x}
        y={y}
        fill={color}
        fontSize={22}
        fontWeight={800}
        letterSpacing={3.6}
        textAnchor="middle"
      >
        {limpio}
      </text>
    </Aparece>
  );
};

/** Estación de computador/pantalla isométrica para dar vida real a los escritorios. */
const MonitorIso: React.FC<{ activo?: boolean; tema?: TemaVisual }> = ({
  activo = false,
  tema = "oscuro",
}) => (
  <g>
    {/* Base soporte */}
    <g transform={en(28, 12, 0)}>
      <Caja w={38} d={24} h={8} tono={activo ? "activo" : "apagado"} tema={tema} grosor={1.6} />
    </g>
    {/* Cuerpo vertical de pantalla */}
    <g transform={en(8, 16, 8)}>
      <Caja
        w={82}
        d={10}
        h={56}
        tono={activo ? "vino" : "apagado"}
        tema={tema}
        grosor={1.8}
      />
    </g>
  </g>
);

// ------------------------------------------------------------------ las cuatro escenas ricas

export type PropsEscena = {
  inicio: number;
  cadencia: number;
  etiquetas: string[];
  tema?: TemaVisual;
  fase?: number;
};

const et = (etiquetas: string[], i: number, porDefecto: string): string =>
  (etiquetas[i] ?? "").trim() || porDefecto;

/**
 * 1. `contraste` — Dos estudios/negocios frente a frente (esqueleto A vs B real).
 * Lado A (izquierda): mesa saturada de carpetas sueltas, pantalla apagada, cruz de fricción.
 * Lado B (derecha): sistema ordenado, pantalla vino encendida, flujo limpio, tarjeta UI + sello.
 */
const EscenaContraste: React.FC<PropsEscena> = ({
  inicio,
  cadencia,
  etiquetas,
  tema = "oscuro",
  fase = 0,
}) => {
  const W = 258;
  const D = 258;
  const H = 26;
  const tLadoA = Math.max(0, inicio - 0.8);
  const tDetalleA = inicio + cadencia * 0.35;
  const tLadoB = inicio + cadencia * 0.95;
  const tResuelto = inicio + cadencia * 1.9;

  // Cámara interna: encuadra A en el dolor inicial, abre a B en la mitad, cierra con ambos + tarjeta
  const focoX = fase === 1 ? 85 : fase >= 2 && fase <= 3 ? -75 : 0;
  const zoomInterno = fase === 1 || fase === 2 ? 1.07 : 1.0;

  const sueltas: [number, number, number, number, number][] = [
    [26, 118, 96, 34, 9],
    [136, 98, 86, 40, 14],
    [48, 174, 152, 38, 10],
    [76, 140, 74, 28, 19],
  ];

  return (
    <g
      transform={`translate(${(ANCHO_ESCENA / 2) * (1 - zoomInterno) + focoX} ${(ALTO_ESCENA / 2) * (1 - zoomInterno)}) scale(${zoomInterno})`}
    >
      {/* ---------------- ESTUDIO A: A LA ANTIGUA / CAOS ---------------- */}
      <g transform="translate(238 308)">
        <Aparece entraEn={tLadoA}>
          <Caja w={W} d={D} h={H} tono="apagado" tema={tema} conSombra />
          {/* Muros bajos de cubículo */}
          <g transform={en(0, 0, H)}>
            <Caja w={W} d={12} h={58} tono="apagado" tema={tema} grosor={1.8} />
          </g>
          <g transform={en(0, 0, H)}>
            <Caja w={12} d={D} h={58} tono="apagado" tema={tema} grosor={1.8} />
          </g>
          <g transform={en(82, 28, H)}>
            <MonitorIso activo={false} tema={tema} />
          </g>
          {sueltas.map(([ox, oy, lw, ld, lh], i) => (
            <g key={`caos-${i}`} transform={en(ox, oy, H)}>
              <Losa w={lw} d={ld} h={lh} tono="apagado" tema={tema} opacidad={0.9} />
            </g>
          ))}
        </Aparece>

        <MarcaAlerta x={-26} y={138} entraEn={tDetalleA} tema={tema} />
        <Tooltip
          x={-18}
          y={-68}
          texto={et(etiquetas, 0, "a ciegas")}
          entraEn={tDetalleA}
          tono="neutro"
          tema={tema}
          apuntaA={[0, 18]}
        />
        <Rotulo x={0} y={288} texto="sin sistema" entraEn={tLadoA + 0.2} tema={tema} />
      </g>

      {/* Conector central de contraste A -> B */}
      <Conector
        desde={[368, 392]}
        hasta={[564, 392]}
        entraEn={tLadoB - 0.25}
        color={PALETA.vinoClaro}
      />

      {/* ---------------- ESTUDIO B: CON EL SOCIO / RESUELTO ---------------- */}
      <g transform="translate(702 308)">
        <Aparece entraEn={tLadoB}>
          <Caja w={W} d={D} h={H} tono="activo" tema={tema} conSombra />
          <g transform={en(0, 0, H)}>
            <Caja w={W} d={12} h={64} tono="activo" tema={tema} grosor={1.8} />
          </g>
          <g transform={en(0, 0, H)}>
            <Caja w={12} d={D} h={64} tono="activo" tema={tema} grosor={1.8} />
          </g>
          {/* Monitor encendido en vino */}
          <g transform={en(86, 28, H)}>
            <MonitorIso activo tema={tema} />
          </g>
          {/* Tres módulos alineados al milímetro */}
          {[104, 152, 200].map((oy, i) => (
            <g key={`orden-${i}`} transform={en(42, oy, H)}>
              <Losa
                w={176}
                d={34}
                h={13}
                tono={i === 2 ? "vino" : "papel"}
                tema={tema}
              />
            </g>
          ))}
        </Aparece>

        <Check x={18} y={142} entraEn={tLadoB + 0.55} tamano={74} />
        <Tooltip
          x={14}
          y={-74}
          texto={et(etiquetas, 1, "resuelto")}
          entraEn={tLadoB + 0.4}
          tono="vino"
          tema={tema}
          apuntaA={[0, 16]}
        />
        <Rotulo x={0} y={288} texto="con el socio" entraEn={tLadoB + 0.25} tema={tema} destacado />
      </g>

      {/* Tarjeta UI de cambio de estado + Sello final */}
      <TarjetaUI
        x={470}
        y={112}
        titulo={et(etiquetas, 2, "entrega clara")}
        estadoTexto="listo sin reprocesos"
        entraEn={tResuelto}
        resuelta
        tema={tema}
      />
      <Sello
        x={730}
        y={525}
        texto={et(etiquetas, 3, "aprobado")}
        entraEn={tResuelto + 0.45}
      />
    </g>
  );
};

/**
 * 2. `flujo` — Tres estaciones conectadas sobre rieles isométricos con paquetes vivos.
 */
const EscenaFlujo: React.FC<PropsEscena> = ({
  inicio,
  cadencia,
  etiquetas,
  tema = "oscuro",
}) => {
  const W = 192;
  const D = 192;
  const H = 24;
  const bases: [number, number][] = [
    [190, 155],
    [470, 316],
    [750, 477],
  ];
  const porDefecto = ["tu problema", "ejecutamos", "entregado"];

  const salida = iso(W, D / 2, H);
  const entrada = iso(0, D / 2, H);
  const cima = iso(0, 0, H);
  const tFinal = inicio + 2.2 * cadencia;

  return (
    <g>
      {bases.map(([bx, by], i) => {
        const tCaja = i === 0 ? Math.max(0, inicio - 0.5) : inicio + (i - 0.15) * cadencia;
        const esCentro = i === 1;
        const esUltima = i === 2;

        return (
          <g key={`estacion-${i}`}>
            {i > 0 ? (
              <Conector
                desde={[bases[i - 1][0] + salida[0], bases[i - 1][1] + salida[1]]}
                hasta={[bx + entrada[0], by + entrada[1]]}
                entraEn={tCaja - cadencia * 0.35}
              />
            ) : null}

            <g transform={`translate(${bx} ${by})`}>
              <Aparece entraEn={tCaja}>
                <Caja
                  w={W}
                  d={D}
                  h={H}
                  tono={esUltima ? "vino" : "activo"}
                  tema={tema}
                  conSombra
                />
                {/* Superestructura distinta en cada estación */}
                {i === 0 ? (
                  <>
                    <g transform={en(36, 36, H)}>
                      <Caja w={120} d={84} h={16} tono="papel" tema={tema} />
                    </g>
                    <g transform={en(46, 134, H)}>
                      <Losa w={96} d={28} h={12} tono="apagado" tema={tema} />
                    </g>
                  </>
                ) : null}

                {esCentro ? (
                  <>
                    <g transform={en(44, 44, H)}>
                      <Caja w={104} d={104} h={46} tono="vino" tema={tema} />
                    </g>
                    <g transform={en(62, 62, H + 46)}>
                      <Caja w={68} d={68} h={20} tono="papel" tema={tema} />
                    </g>
                  </>
                ) : null}

                {esUltima ? (
                  <>
                    <g transform={en(34, 42, H)}>
                      <Caja w={124} d={108} h={26} tono="papel" tema={tema} />
                    </g>
                    <Check x={0} y={84} entraEn={tCaja + 0.45} tamano={66} />
                  </>
                ) : null}
              </Aparece>
            </g>

            <Tooltip
              x={bx}
              y={by + cima[1] - 68}
              texto={et(etiquetas, i, porDefecto[i])}
              entraEn={tCaja + 0.25}
              tono={esUltima ? "vino" : "neutro"}
              tema={tema}
              apuntaA={[bx, by + cima[1] - 10]}
            />
          </g>
        );
      })}

      <TarjetaUI
        x={685}
        y={155}
        titulo="proceso completo"
        estadoTexto={et(etiquetas, 3, "listo para operar")}
        entraEn={tFinal}
        resuelta
        tema={tema}
      />
    </g>
  );
};

/**
 * 3. `espacio3d` — Maqueta arquitectónica completa: retícula CAD -> muros -> isla vino + mobiliario + luz.
 */
const EscenaEspacio3d: React.FC<PropsEscena> = ({
  inicio,
  cadencia,
  etiquetas,
  tema = "oscuro",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const LADO = 456;
  const PASO = LADO / 6;
  const MURO = 172;
  const tPlano = Math.max(0, inicio - 0.6);
  const tMuros = inicio + cadencia * 0.55;
  const tMuebles = inicio + cadencia * 1.35;
  const tSello = inicio + cadencia * 2.1;

  const subida = (desde: number, alto: number, dur = 0.7) =>
    interpolate(frame, [desde * fps, (desde + dur) * fps], [0, alto], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.out(Easing.cubic),
    });

  const hMuro = subida(tMuros, MURO);
  const hIsla = subida(tMuebles, 64);
  const hEstante = subida(tMuebles + 0.2, 92);
  const lineas = Array.from({ length: 7 }, (_, i) => i * PASO);
  const esCrema = tema === "crema";

  return (
    <g transform="translate(470 250)">
      <Aparece entraEn={tPlano}>
        {/* Losa arquitectónica con espesor 3D */}
        <Caja w={LADO} d={LADO} h={18} tono="activo" tema={tema} conSombra />
        {/* Grilla CAD sobre la losa (z = 18) */}
        {lineas.map((v) => (
          <g key={`cad-${v}`} opacity={esCrema ? 0.32 : 0.38}>
            <line
              x1={iso(v, 0, 18)[0]}
              y1={iso(v, 0, 18)[1]}
              x2={iso(v, LADO, 18)[0]}
              y2={iso(v, LADO, 18)[1]}
              stroke={esCrema ? PALETA.tinta : PALETA.grisClaro}
              strokeWidth={1.2}
            />
            <line
              x1={iso(0, v, 18)[0]}
              y1={iso(0, v, 18)[1]}
              x2={iso(LADO, v, 18)[0]}
              y2={iso(LADO, v, 18)[1]}
              stroke={esCrema ? PALETA.tinta : PALETA.grisClaro}
              strokeWidth={1.2}
            />
          </g>
        ))}
      </Aparece>

      {/* Muros perimetrales con grosor arquitectónico y vano de ventana */}
      {hMuro > 2 ? (
        <g>
          <g transform={en(0, 0, 18)}>
            <Caja w={LADO} d={18} h={hMuro} tono="activo" tema={tema} />
          </g>
          <g transform={en(0, 0, 18)}>
            <Caja w={18} d={LADO} h={hMuro} tono="activo" tema={tema} />
          </g>
          {/* Ventanal luminoso en muro derecho */}
          {hMuro > 110 ? (
            <polygon
              points={`${pt(130, 19, 68)} ${pt(330, 19, 68)} ${pt(330, 19, Math.min(hMuro - 12, 150))} ${pt(130, 19, Math.min(hMuro - 12, 150))}`}
              fill={PALETA.vinoClaro}
              fillOpacity={0.28}
              stroke={esCrema ? PALETA.tinta : PALETA.blanco}
              strokeWidth={2}
            />
          ) : null}
        </g>
      ) : null}

      {/* Mobiliario interior: estantería + isla principal vino + mesas auxiliares */}
      {hEstante > 2 ? (
        <g transform={en(22, 90, 18)}>
          <Caja w={44} d={190} h={hEstante} tono="papel" tema={tema} />
        </g>
      ) : null}

      {hIsla > 2 ? (
        <g>
          {/* Isla central / mostrador protagonista */}
          <g transform={en(155, 165, 18)}>
            <Caja w={185} d={110} h={hIsla} tono="vino" tema={tema} conSombra />
          </g>
          {/* Cubierta de barra sobre la isla */}
          {hIsla > 50 ? (
            <g transform={en(148, 158, 18 + hIsla)}>
              <Losa w={199} d={124} h={10} tono="papel" tema={tema} />
            </g>
          ) : null}
          {/* Dos módulos / asientos frente a la isla */}
          <g transform={en(185, 320, 18)}>
            <Caja w={48} d={48} h={Math.min(38, hIsla)} tono="activo" tema={tema} />
          </g>
          <g transform={en(265, 320, 18)}>
            <Caja w={48} d={48} h={Math.min(38, hIsla)} tono="activo" tema={tema} />
          </g>
        </g>
      ) : null}

      <Tooltip
        x={-285}
        y={-42}
        texto={et(etiquetas, 0, "tu plano")}
        entraEn={tPlano + 0.3}
        tema={tema}
        apuntaA={[iso(0, LADO * 0.55, 18)[0], iso(0, LADO * 0.55, 18)[1]]}
      />
      <Tooltip
        x={255}
        y={-95}
        texto={et(etiquetas, 1, "vista real")}
        entraEn={tMuebles + 0.35}
        tono="vino"
        tema={tema}
        apuntaA={[iso(245, 210, 86)[0], iso(245, 210, 86)[1]]}
      />
      <Sello x={265} y={305} texto={et(etiquetas, 2, "sin sorpresas")} entraEn={tSello} />
    </g>
  );
};

/**
 * 4. `agenda` — Bandeja saturada -> Prospecto calificado -> Calendario 3D bloqueado.
 */
const EscenaAgenda: React.FC<PropsEscena> = ({
  inicio,
  cadencia,
  etiquetas,
  tema = "oscuro",
}) => {
  const tBandeja = Math.max(0, inicio - 0.5);
  const tCliente = inicio + cadencia * 0.85;
  const tAgenda = inicio + cadencia * 1.75;

  const bandeja = { x: 195, y: 135, w: 205, d: 205, h: 20 };
  const cliente = { x: 468, y: 292, w: 196, d: 196, h: 22 };
  const agenda = { x: 742, y: 452, w: 206, d: 206, h: 22 };

  const salida = (c: typeof bandeja) => iso(c.w, c.d / 2, c.h);
  const entrada = (c: typeof bandeja) => iso(0, c.d / 2, c.h);
  const cima = (c: typeof bandeja) => iso(0, 0, c.h);

  const celdas: [number, number, boolean][] = [];
  for (let f = 0; f < 3; f++) {
    for (let c = 0; c < 4; c++) {
      celdas.push([20 + c * 42, 48 + f * 44, f === 1 && c === 2]);
    }
  }

  return (
    <g>
      {/* 1. Bandeja de mensajes entrantes */}
      <g transform={`translate(${bandeja.x} ${bandeja.y})`}>
        <Aparece entraEn={tBandeja}>
          <Caja w={bandeja.w} d={bandeja.d} h={bandeja.h} tono="apagado" tema={tema} conSombra />
          {[0, 1, 2].map((i) => (
            <g key={`sobre-${i}`} transform={en(24 + i * 8, 26 + i * 54, bandeja.h + i * 8)}>
              <Losa
                w={150}
                d={40}
                h={12}
                tono={i === 2 ? "papel" : "apagado"}
                tema={tema}
              />
            </g>
          ))}
        </Aparece>
        <Rotulo x={0} y={248} texto={et(etiquetas, 0, "mensajes")} entraEn={tBandeja + 0.25} tema={tema} />
      </g>

      <Conector
        desde={[bandeja.x + salida(bandeja)[0], bandeja.y + salida(bandeja)[1]]}
        hasta={[cliente.x + entrada(cliente)[0], cliente.y + entrada(cliente)[1]]}
        entraEn={tCliente - cadencia * 0.35}
      />

      {/* 2. Filtro de calificación */}
      <g transform={`translate(${cliente.x} ${cliente.y})`}>
        <Aparece entraEn={tCliente}>
          <Caja w={cliente.w} d={cliente.d} h={cliente.h} tono="activo" tema={tema} conSombra />
          <g transform={en(26, 30, cliente.h)}>
            <Losa w={144} d={42} h={14} tono="vino" tema={tema} />
          </g>
          <g transform={en(26, 90, cliente.h)}>
            <Losa w={144} d={32} h={11} tono="papel" tema={tema} />
          </g>
          <g transform={en(26, 136, cliente.h)}>
            <Losa w={104} d={28} h={11} tono="papel" tema={tema} />
          </g>
        </Aparece>
        <Check x={0} y={145} entraEn={tCliente + 0.45} tamano={68} />
        <Rotulo
          x={0}
          y={236}
          texto={et(etiquetas, 1, "calificado")}
          entraEn={tCliente + 0.3}
          tema={tema}
          destacado
        />
      </g>

      <Conector
        desde={[cliente.x + salida(cliente)[0], cliente.y + salida(cliente)[1]]}
        hasta={[agenda.x + entrada(agenda)[0], agenda.y + entrada(agenda)[1]]}
        entraEn={tAgenda - cadencia * 0.35}
      />

      {/* 3. Tablero de calendario 3D con bloque vino elevado */}
      <g transform={`translate(${agenda.x} ${agenda.y})`}>
        <Aparece entraEn={tAgenda}>
          <Caja w={agenda.w} d={agenda.d} h={agenda.h} tono="activo" tema={tema} conSombra />
          {/* Cabezal vino del calendario */}
          <g transform={en(12, 12, agenda.h)}>
            <Losa w={agenda.w - 24} d={24} h={10} tono="vino" tema={tema} />
          </g>
          {celdas.map(([ox, oy, marcada], i) => (
            <g key={`dia-${i}`} transform={en(ox, oy, agenda.h)}>
              <Losa
                w={34}
                d={34}
                h={marcada ? 26 : 8}
                tono={marcada ? "vino" : "papel"}
                tema={tema}
                opacidad={marcada ? 1 : 0.78}
              />
            </g>
          ))}
        </Aparece>
        <Sello
          x={cima(agenda)[0]}
          y={cima(agenda)[1] - 42}
          texto={et(etiquetas, 2, "agendado")}
          entraEn={tAgenda + 0.55}
          tamano={26}
        />
      </g>

      <TarjetaUI
        x={655}
        y={145}
        titulo="cita lista"
        estadoTexto="solo cierras tú"
        entraEn={tAgenda + 0.3}
        resuelta
        tema={tema}
      />
    </g>
  );
};

const ESCENAS: Record<NombreEscena, React.FC<PropsEscena>> = {
  contraste: EscenaContraste,
  flujo: EscenaFlujo,
  espacio3d: EscenaEspacio3d,
  agenda: EscenaAgenda,
};

export const EscenaIsometrica: React.FC<
  PropsEscena & { escena?: NombreEscena; estilo?: React.CSSProperties }
> = ({ escena = "contraste", inicio, cadencia, etiquetas, tema = "oscuro", fase = 0, estilo }) => {
  const Elegida = ESCENAS[escena] ?? EscenaContraste;
  return (
    <svg
      viewBox={`0 0 ${ANCHO_ESCENA} ${ALTO_ESCENA}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ width: "100%", height: "100%", fontFamily: FUENTE_ESCENA, overflow: "visible", ...estilo }}
    >
      <Elegida inicio={inicio} cadencia={cadencia} etiquetas={etiquetas} tema={tema} fase={fase} />
    </svg>
  );
};
