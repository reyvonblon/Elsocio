import React from "react";
import { Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

/**
 * Escenas isométricas de El Socio. SVG geométrico puro, cero dependencias, 0 USD por render.
 *
 * Por qué en código y no como imagen generada: una ilustración generada hay que volver a
 * generarla (y pagarla) cada vez que cambia una palabra. Esto se reusa con props.
 *
 * Reglas que cumplen las cuatro escenas (de `contexto/guia-estilo-video.md`):
 *  - Proyección isométrica real de 30°: ángulos limpios, cero perspectiva, cero deformación.
 *  - Paleta de El Socio y nada más: tinta, carbón, blanco, gris, vino.
 *  - Un elemento héroe por escena; el resto entra y se queda quieto (las referencias están
 *    quietas 61-75% del tiempo: la calidad la pone el ritmo de entrada, no el movimiento).
 *  - Etiquetas flotantes tipo tooltip con el dato cualitativo.
 *  - CERO cifras: ni precios, ni plazos, ni porcentajes, ni medidas. Las etiquetas que
 *    llegan por props las valida `content_manager.py` con la guarda de precios en código.
 */

export const PALETA = {
  tinta: "#0a0a0a",
  carbon: "#151517",
  blanco: "#ffffff",
  gris: "#6e6e73",
  vino: "#9c1c2e",
  vinoClaro: "#b22337",
} as const;

export const FUENTE_ESCENA =
  "-apple-system,BlinkMacSystemFont,'SF Pro Text','Segoe UI',Helvetica,Arial,sans-serif";

/** Lienzo común de las cuatro escenas. Todo está dibujado para caber aquí dentro. */
export const ANCHO_ESCENA = 920;
export const ALTO_ESCENA = 700;

export const NOMBRES_ESCENA = ["contraste", "flujo", "espacio3d", "agenda"] as const;
export type NombreEscena = (typeof NOMBRES_ESCENA)[number];

// ------------------------------------------------------------------ proyección isométrica

const COS30 = 0.8660254037844387;

/** Punto del espacio (x hacia la derecha-abajo, y hacia la izquierda-abajo, z hacia arriba). */
export const iso = (x: number, y: number, z = 0): [number, number] => [
  (x - y) * COS30,
  (x + y) * 0.5 - z,
];

const pt = (x: number, y: number, z = 0): string => {
  const [sx, sy] = iso(x, y, z);
  return `${sx.toFixed(2)},${sy.toFixed(2)}`;
};

/** Mueve un `<g>` a un punto del espacio isométrico (para apilar cosas encima de una caja). */
const en = (x: number, y: number, z = 0): string => {
  const [sx, sy] = iso(x, y, z);
  return `translate(${sx.toFixed(2)} ${sy.toFixed(2)})`;
};

// ------------------------------------------------------------------ piezas reutilizables

type Tono = "apagado" | "activo" | "vino";

const BORDE: Record<Tono, string> = {
  apagado: PALETA.gris,
  activo: PALETA.blanco,
  vino: PALETA.vinoClaro,
};
/** Velo blanco sobre la cara superior: es lo que lee como "iluminado" sin salirse de la paleta. */
const LUZ: Record<Tono, number> = { apagado: 0, activo: 0.09, vino: 0.04 };

type CajaProps = {
  w: number;
  d: number;
  h: number;
  tono?: Tono;
  /** Relleno de la cara superior. Por defecto carbón; vino para los sellos de estado. */
  cara?: string;
  grosor?: number;
  opacidad?: number;
};

/**
 * Caja isométrica: cara superior + los dos laterales que ve la cámara.
 * Los laterales van en tinta para que la sombra salga de la paleta, no de un gradiente.
 */
const Caja: React.FC<CajaProps> = ({
  w,
  d,
  h,
  tono = "apagado",
  cara = PALETA.carbon,
  grosor = 2,
  opacidad = 1,
}) => (
  <g opacity={opacidad}>
    <polygon
      points={`${pt(0, d, h)} ${pt(w, d, h)} ${pt(w, d, 0)} ${pt(0, d, 0)}`}
      fill={PALETA.tinta}
      stroke={BORDE[tono]}
      strokeWidth={grosor}
      strokeLinejoin="round"
    />
    <polygon
      points={`${pt(w, 0, h)} ${pt(w, d, h)} ${pt(w, d, 0)} ${pt(w, 0, 0)}`}
      fill={PALETA.tinta}
      fillOpacity={0.55}
      stroke={BORDE[tono]}
      strokeWidth={grosor}
      strokeLinejoin="round"
    />
    <polygon
      points={`${pt(0, 0, h)} ${pt(w, 0, h)} ${pt(w, d, h)} ${pt(0, d, h)}`}
      fill={cara}
      stroke={BORDE[tono]}
      strokeWidth={grosor}
      strokeLinejoin="round"
    />
    {LUZ[tono] > 0 ? (
      <polygon
        points={`${pt(0, 0, h)} ${pt(w, 0, h)} ${pt(w, d, h)} ${pt(0, d, h)}`}
        fill={PALETA.blanco}
        opacity={LUZ[tono]}
      />
    ) : null}
  </g>
);

/** Losa plana sobre una cara: barras de datos, tarjetas apiladas, celdas de calendario. */
const Losa: React.FC<{
  w: number;
  d: number;
  h?: number;
  tono?: Tono;
  cara?: string;
  opacidad?: number;
}> = ({ w, d, h = 10, tono = "apagado", cara = PALETA.carbon, opacidad = 1 }) => (
  <Caja w={w} d={d} h={h} tono={tono} cara={cara} grosor={1.6} opacidad={opacidad} />
);

/** Entrada con `spring`: sube y aparece. Nada rebota de más: sobriedad por encima de todo. */
const Aparece: React.FC<{
  entraEn: number;
  sube?: number;
  children: React.ReactNode;
}> = ({ entraEn, sube = 44, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const inicio = Math.round(entraEn * fps);
  if (frame < inicio) return null;
  const t = spring({ frame: frame - inicio, fps, config: { damping: 200, mass: 0.6 } });
  return (
    <g opacity={t} transform={`translate(0 ${((1 - t) * sube).toFixed(2)})`}>
      {children}
    </g>
  );
};

/** Etiqueta flotante tipo tooltip, con guía fina hasta el punto que señala. */
const Tooltip: React.FC<{
  x: number;
  y: number;
  texto: string;
  entraEn: number;
  /** Punto al que apunta la guía; si no se pasa, no dibuja guía. */
  apuntaA?: [number, number];
  tono?: "tinta" | "vino";
  tamano?: number;
}> = ({ x, y, texto, entraEn, apuntaA, tono = "tinta", tamano = 22 }) => {
  const limpio = (texto || "").trim().toUpperCase();
  if (!limpio) return null;
  const espaciado = 1.6;
  const ancho = limpio.length * (tamano * 0.64 + espaciado) + 38;
  const alto = tamano + 20;
  const vino = tono === "vino";

  return (
    <Aparece entraEn={entraEn} sube={18}>
      {apuntaA ? (
        <line
          x1={x}
          y1={y + alto / 2}
          x2={apuntaA[0]}
          y2={apuntaA[1]}
          stroke={vino ? PALETA.vinoClaro : PALETA.gris}
          strokeWidth={1.6}
          strokeDasharray="5 5"
        />
      ) : null}
      <rect
        x={x - ancho / 2}
        y={y - alto / 2}
        width={ancho}
        height={alto}
        rx={alto / 2}
        fill={vino ? PALETA.vino : PALETA.carbon}
        stroke={vino ? PALETA.vinoClaro : PALETA.gris}
        strokeWidth={1.8}
      />
      <text
        x={x}
        y={y}
        fill={PALETA.blanco}
        fontSize={tamano}
        fontWeight={700}
        letterSpacing={espaciado}
        textAnchor="middle"
        dominantBaseline="central"
      >
        {limpio}
      </text>
    </Aparece>
  );
};

/** Sello estampado: entra grande y se asienta. Uno por escena, nunca dos. */
const Sello: React.FC<{
  x: number;
  y: number;
  texto: string;
  entraEn: number;
  rotacion?: number;
  tamano?: number;
}> = ({ x, y, texto, entraEn, rotacion = -8, tamano = 30 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const limpio = (texto || "").trim().toUpperCase();
  const inicio = Math.round(entraEn * fps);
  if (!limpio || frame < inicio) return null;

  const t = spring({ frame: frame - inicio, fps, config: { damping: 14, mass: 0.9 } });
  const escala = interpolate(t, [0, 1], [1.7, 1]);
  const espaciado = 3;
  const ancho = limpio.length * (tamano * 0.68 + espaciado) + 46;
  const alto = tamano + 28;

  return (
    <g
      opacity={Math.min(1, t * 1.6)}
      transform={`translate(${x} ${y}) rotate(${rotacion}) scale(${escala.toFixed(3)})`}
    >
      <rect
        x={-ancho / 2}
        y={-alto / 2}
        width={ancho}
        height={alto}
        rx={8}
        fill={PALETA.vino}
        stroke={PALETA.vinoClaro}
        strokeWidth={3}
      />
      <rect
        x={-ancho / 2 + 7}
        y={-alto / 2 + 7}
        width={ancho - 14}
        height={alto - 14}
        rx={4}
        fill="none"
        stroke={PALETA.blanco}
        strokeWidth={1.6}
        opacity={0.5}
      />
      <text
        x={0}
        y={0}
        fill={PALETA.blanco}
        fontSize={tamano}
        fontWeight={800}
        letterSpacing={espaciado}
        textAnchor="middle"
        dominantBaseline="central"
      >
        {limpio}
      </text>
    </g>
  );
};

/** Conector trazado progresivamente, con punta de flecha cuando termina de dibujarse. */
const Conector: React.FC<{
  desde: [number, number];
  hasta: [number, number];
  entraEn: number;
  duracion?: number;
  color?: string;
  ancho?: number;
}> = ({ desde, hasta, entraEn, duracion = 0.55, color = PALETA.vinoClaro, ancho = 5 }) => {
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
      {avance > 0.97 ? (
        <polygon
          points={[
            `${x2},${y2}`,
            `${x2 - ux * a - uy * b},${y2 - uy * a + ux * b}`,
            `${x2 - ux * a + uy * b},${y2 - uy * a - ux * b}`,
          ].join(" ")}
          fill={color}
        />
      ) : null}
    </g>
  );
};

/** Marca de verificación, dibujada progresivamente. El "ya está resuelto" de la escena. */
const Check: React.FC<{ x: number; y: number; entraEn: number; tamano?: number }> = ({
  x,
  y,
  entraEn,
  tamano = 64,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const inicio = entraEn * fps;
  const avance = interpolate(frame, [inicio, inicio + 0.45 * fps], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  if (avance >= 1) return null;
  const s = tamano / 64;

  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <circle r={30} fill={PALETA.vino} stroke={PALETA.vinoClaro} strokeWidth={3} />
      <path
        d="M -14 1 L -4 12 L 15 -11"
        fill="none"
        stroke={PALETA.blanco}
        strokeWidth={6}
        strokeLinecap="round"
        strokeLinejoin="round"
        pathLength={1}
        strokeDasharray={1}
        strokeDashoffset={avance}
      />
    </g>
  );
};

/** Rótulo pequeño al pie de una pieza. Sin caja: no compite con los tooltips. */
const Rotulo: React.FC<{
  x: number;
  y: number;
  texto: string;
  entraEn: number;
  color?: string;
}> = ({ x, y, texto, entraEn, color = PALETA.gris }) => {
  const limpio = (texto || "").trim().toUpperCase();
  if (!limpio) return null;
  return (
    <Aparece entraEn={entraEn} sube={12}>
      <text
        x={x}
        y={y}
        fill={color}
        fontSize={23}
        fontWeight={700}
        letterSpacing={4}
        textAnchor="middle"
      >
        {limpio}
      </text>
    </Aparece>
  );
};

// ------------------------------------------------------------------ las cuatro escenas

export type PropsEscena = {
  /** Segundo en que la escena empieza a montarse (normalmente, cuando acaba el gancho). */
  inicio: number;
  /** Segundos entre bloques del guion: la escena respira al mismo ritmo que el texto. */
  cadencia: number;
  /** Tooltips. Si viene vacío, cada escena usa los suyos. Validados en `content_manager.py`. */
  etiquetas: string[];
};

const et = (etiquetas: string[], i: number, porDefecto: string): string =>
  (etiquetas[i] ?? "").trim() || porDefecto;

/**
 * `contraste` — el esqueleto A vs B que repiten las 3 referencias.
 * Izquierda: la misma plataforma, apagada y con el trabajo desordenado encima.
 * Derecha: iluminada, alineada, con check vino y la etiqueta de estado.
 */
const EscenaContraste: React.FC<PropsEscena> = ({ inicio, cadencia, etiquetas }) => {
  const W = 230;
  const D = 230;
  const H = 24;
  const tB = inicio + cadencia * 0.9;

  // Desordenado = tamaños y huecos irregulares. Nada rotado: el ángulo isométrico no se rompe.
  const sueltas: [number, number, number, number][] = [
    [34, 36, 146, 32],
    [63, 104, 87, 27],
    [24, 155, 172, 36],
  ];
  // Resuelto = tres barras idénticas, mismo paso, mismo borde.
  const ordenadas = [32, 92, 152];

  return (
    <g>
      <g transform="translate(215 330)">
        <Aparece entraEn={inicio}>
          <Caja w={W} d={D} h={H} tono="apagado" opacidad={0.85} />
          {sueltas.map(([ox, oy, lw, ld], i) => (
            <g key={`suelta-${i}`} transform={en(ox, oy, H)}>
              <Losa w={lw} d={ld} h={8} tono="apagado" opacidad={0.7} />
            </g>
          ))}
        </Aparece>
        <Rotulo x={0} y={272} texto="antes" entraEn={inicio + 0.3} />
      </g>

      <g transform="translate(700 300)">
        <Aparece entraEn={tB}>
          <Caja w={W} d={D} h={H} tono="activo" />
          {ordenadas.map((oy, i) => (
            <g key={`orden-${i}`} transform={en(34, oy, H)}>
              <Losa w={162} d={36} h={10} tono="activo" />
            </g>
          ))}
        </Aparece>
        <Check x={0} y={118} entraEn={tB + 0.5} tamano={84} />
        <Rotulo x={0} y={272} texto="ahora" entraEn={tB + 0.3} color={PALETA.blanco} />
      </g>

      <Tooltip
        x={700}
        y={140}
        texto={et(etiquetas, 0, "resuelto")}
        entraEn={tB + 0.85}
        tono="vino"
        apuntaA={[700, 290]}
      />
    </g>
  );
};

/**
 * `flujo` — los tres pasos, uno por bloque del guion.
 * Las cajas caminan por el eje +x del isométrico, así el conector cae sobre la grilla
 * y las diagonales quedan a 30° exactos en vez de "casi".
 */
const EscenaFlujo: React.FC<PropsEscena> = ({ inicio, cadencia, etiquetas }) => {
  const W = 170;
  const D = 170;
  const H = 20;
  const bases: [number, number][] = [
    [175, 130],
    [452, 290],
    [729, 450],
  ];
  const porDefecto = ["1. cuentas", "2. resolvemos", "3. entregado"];

  // Salida e entrada del conector: los centros de las caras x=W y x=0, a media altura.
  const salida = iso(W, D / 2, H);
  const entrada = iso(0, D / 2, H);
  const cima = iso(0, 0, H);

  return (
    <g>
      {bases.map(([bx, by], i) => {
        const tCaja = inicio + i * cadencia;
        const ultima = i === bases.length - 1;
        return (
          <g key={`paso-${i}`}>
            {i > 0 ? (
              <Conector
                desde={[bases[i - 1][0] + salida[0], bases[i - 1][1] + salida[1]]}
                hasta={[bx + entrada[0], by + entrada[1]]}
                entraEn={tCaja - cadencia * 0.45}
              />
            ) : null}
            <g transform={`translate(${bx} ${by})`}>
              <Aparece entraEn={tCaja}>
                <Caja
                  w={W}
                  d={D}
                  h={H}
                  tono={ultima ? "vino" : "activo"}
                  cara={ultima ? PALETA.vino : PALETA.carbon}
                />
              </Aparece>
            </g>
            <Tooltip
              x={bx}
              y={by + cima[1] - 48}
              texto={et(etiquetas, i, porDefecto[i])}
              entraEn={tCaja + 0.35}
              tono={ultima ? "vino" : "tinta"}
              apuntaA={[bx, by + cima[1]]}
            />
          </g>
        );
      })}
    </g>
  );
};

/**
 * `espacio3d` — el nicho de modelado: un plano que se convierte en volumen.
 * Las líneas de proyección existen para que se lea como render técnico; van SIN medidas,
 * porque una medida en pantalla ya es una promesa (`guia-estilo-video.md` §4).
 */
const EscenaEspacio3d: React.FC<PropsEscena> = ({ inicio, cadencia, etiquetas }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const LADO = 440;
  const PASO = LADO / 6;
  const MURO = 155;
  const tMuros = inicio + cadencia * 0.8;
  const tVolumen = inicio + cadencia * 1.6;

  const subida = (desde: number, alto: number) =>
    interpolate(frame, [desde * fps, (desde + 0.8) * fps], [0, alto], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.out(Easing.cubic),
    });

  const hMuro = subida(tMuros, MURO);
  const hVol = subida(tVolumen, 65);
  const lineas = Array.from({ length: 7 }, (_, i) => i * PASO);
  const proyeccion = interpolate(frame, [tMuros * fps, (tMuros + 1) * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <g transform="translate(460 240)">
      <Aparece entraEn={inicio}>
        {/* Plano: el suelo y su grilla, dibujados con los mismos dos ejes del isométrico. */}
        <polygon
          points={`${pt(0, 0)} ${pt(LADO, 0)} ${pt(LADO, LADO)} ${pt(0, LADO)}`}
          fill={PALETA.carbon}
          stroke={PALETA.gris}
          strokeWidth={2}
        />
        {lineas.map((v) => (
          <g key={`g-${v}`} opacity={0.4}>
            <line
              x1={iso(v, 0)[0]}
              y1={iso(v, 0)[1]}
              x2={iso(v, LADO)[0]}
              y2={iso(v, LADO)[1]}
              stroke={PALETA.gris}
              strokeWidth={1}
            />
            <line
              x1={iso(0, v)[0]}
              y1={iso(0, v)[1]}
              x2={iso(LADO, v)[0]}
              y2={iso(LADO, v)[1]}
              stroke={PALETA.gris}
              strokeWidth={1}
            />
          </g>
        ))}
      </Aparece>

      {/* Muros: suben desde las dos aristas del fondo. Un solo gesto, sin rebote. */}
      {hMuro > 1 ? (
        <g>
          <polygon
            points={`${pt(0, 0, 0)} ${pt(LADO, 0, 0)} ${pt(LADO, 0, hMuro)} ${pt(0, 0, hMuro)}`}
            fill={PALETA.tinta}
            fillOpacity={0.92}
            stroke={PALETA.blanco}
            strokeWidth={2}
            strokeLinejoin="round"
          />
          <polygon
            points={`${pt(0, 0, 0)} ${pt(0, LADO, 0)} ${pt(0, LADO, hMuro)} ${pt(0, 0, hMuro)}`}
            fill={PALETA.carbon}
            stroke={PALETA.blanco}
            strokeWidth={2}
            strokeLinejoin="round"
          />
        </g>
      ) : null}

      {/* Volumen dentro del espacio: el "mueble" que convierte el plano en render. */}
      {hVol > 1 ? (
        <g transform={en(175, 225, 0)}>
          <Caja w={135} d={105} h={hVol} tono="vino" cara={PALETA.vino} />
        </g>
      ) : null}

      {/* Líneas de proyección: punteadas, de cota, SIN número. */}
      <g opacity={proyeccion * 0.75}>
        {([
          [LADO, 0],
          [0, LADO],
        ] as [number, number][]).map(([px, py], i) => {
          const [bx, by] = iso(px, py, 0);
          const [tx, ty] = iso(px, py, MURO + 65);
          return (
            <g key={`proy-${i}`}>
              <line
                x1={bx}
                y1={by}
                x2={tx}
                y2={ty}
                stroke={PALETA.gris}
                strokeWidth={1.4}
                strokeDasharray="7 7"
              />
              <line
                x1={tx - 12}
                y1={ty}
                x2={tx + 12}
                y2={ty}
                stroke={PALETA.gris}
                strokeWidth={1.4}
              />
            </g>
          );
        })}
        <line
          x1={iso(LADO, 0, MURO + 65)[0]}
          y1={iso(LADO, 0, MURO + 65)[1]}
          x2={iso(0, 0, MURO + 65)[0]}
          y2={iso(0, 0, MURO + 65)[1]}
          stroke={PALETA.gris}
          strokeWidth={1.4}
          strokeDasharray="7 7"
        />
      </g>

      <Tooltip
        x={-280}
        y={-40}
        texto={et(etiquetas, 0, "tu plano")}
        entraEn={inicio + 0.4}
        apuntaA={[iso(0, LADO / 2)[0], iso(0, LADO / 2)[1]]}
      />
      <Sello x={280} y={-30} texto={et(etiquetas, 1, "render")} entraEn={tVolumen + 0.5} />
    </g>
  );
};

/**
 * `agenda` — el único resultado que el agente promete: cliente calificado en el calendario.
 * Bandeja de mensajes → tarjeta del que sí califica → día bloqueado con sello.
 */
const EscenaAgenda: React.FC<PropsEscena> = ({ inicio, cadencia, etiquetas }) => {
  const tCliente = inicio + cadencia * 0.9;
  const tAgenda = inicio + cadencia * 1.8;

  const bandeja = { x: 195, y: 110, w: 210, d: 210, h: 16 };
  const cliente = { x: 462, y: 275, w: 186, d: 186, h: 18 };
  const agenda = { x: 735, y: 440, w: 186, d: 186, h: 18 };

  const salida = (c: typeof bandeja) => iso(c.w, c.d / 2, c.h);
  const entrada = (c: typeof bandeja) => iso(0, c.d / 2, c.h);
  const cima = (c: typeof bandeja) => iso(0, 0, c.h);

  // Celdas del calendario: 4 x 3 sobre la cara superior, una en vino (el día que se bloqueó).
  const celdas: [number, number, boolean][] = [];
  for (let f = 0; f < 3; f++) {
    for (let c = 0; c < 4; c++) {
      celdas.push([22 + c * 35, 38 + f * 38, f === 1 && c === 2]);
    }
  }

  return (
    <g>
      {/* 1. La bandeja: mensajes que entran, todavía sin clasificar. */}
      <g transform={`translate(${bandeja.x} ${bandeja.y})`}>
        <Aparece entraEn={inicio}>
          <Caja w={bandeja.w} d={bandeja.d} h={bandeja.h} tono="apagado" />
          {[0, 1, 2].map((i) => (
            <g key={`msg-${i}`} transform={en(32 + i * 6, 32 + i * 55, bandeja.h + i * 10)}>
              <Losa w={158} d={42} h={9} tono="apagado" opacidad={0.8} />
            </g>
          ))}
        </Aparece>
        <Rotulo x={0} y={248} texto={et(etiquetas, 0, "entran")} entraEn={inicio + 0.3} />
      </g>

      <Conector
        desde={[bandeja.x + salida(bandeja)[0], bandeja.y + salida(bandeja)[1]]}
        hasta={[cliente.x + entrada(cliente)[0], cliente.y + entrada(cliente)[1]]}
        entraEn={tCliente - cadencia * 0.45}
      />

      {/* 2. El que sí califica: una sola tarjeta, iluminada, con check. */}
      <g transform={`translate(${cliente.x} ${cliente.y})`}>
        <Aparece entraEn={tCliente}>
          <Caja w={cliente.w} d={cliente.d} h={cliente.h} tono="activo" />
          <g transform={en(30, 36, cliente.h)}>
            <Losa w={128} d={32} h={9} tono="activo" />
          </g>
          <g transform={en(30, 92, cliente.h)}>
            <Losa w={90} d={28} h={9} tono="activo" opacidad={0.75} />
          </g>
        </Aparece>
        <Check x={0} y={140} entraEn={tCliente + 0.5} tamano={68} />
        <Rotulo
          x={0}
          y={216}
          texto={et(etiquetas, 1, "califica")}
          entraEn={tCliente + 0.35}
          color={PALETA.blanco}
        />
      </g>

      <Conector
        desde={[cliente.x + salida(cliente)[0], cliente.y + salida(cliente)[1]]}
        hasta={[agenda.x + entrada(agenda)[0], agenda.y + entrada(agenda)[1]]}
        entraEn={tAgenda - cadencia * 0.45}
      />

      {/* 3. El calendario: el día ya está bloqueado. Aquí para el agente. */}
      <g transform={`translate(${agenda.x} ${agenda.y})`}>
        <Aparece entraEn={tAgenda}>
          <Caja w={agenda.w} d={agenda.d} h={agenda.h} tono="activo" />
          {celdas.map(([ox, oy, marcada], i) => (
            <g key={`celda-${i}`} transform={en(ox, oy, agenda.h)}>
              <polygon
                points={`${pt(0, 0)} ${pt(28, 0)} ${pt(28, 30)} ${pt(0, 30)}`}
                fill={marcada ? PALETA.vino : PALETA.tinta}
                stroke={marcada ? PALETA.vinoClaro : PALETA.gris}
                strokeWidth={1.2}
                opacity={marcada ? 1 : 0.55}
              />
            </g>
          ))}
        </Aparece>
        <Sello
          x={cima(agenda)[0]}
          y={cima(agenda)[1] + 80}
          texto={et(etiquetas, 2, "agendado")}
          entraEn={tAgenda + 0.6}
          tamano={28}
        />
      </g>
    </g>
  );
};

const ESCENAS: Record<NombreEscena, React.FC<PropsEscena>> = {
  contraste: EscenaContraste,
  flujo: EscenaFlujo,
  espacio3d: EscenaEspacio3d,
  agenda: EscenaAgenda,
};

/**
 * Punto de entrada: elige la escena y la mete en el lienzo común.
 * `preserveAspectRatio="xMidYMid meet"` es lo que garantiza que nada se salga del hueco
 * que le da `ReelVertical` — y por tanto, de las zonas seguras de Reels.
 */
export const EscenaIsometrica: React.FC<
  PropsEscena & { escena?: NombreEscena; estilo?: React.CSSProperties }
> = ({ escena = "contraste", inicio, cadencia, etiquetas, estilo }) => {
  const Elegida = ESCENAS[escena] ?? EscenaContraste;
  return (
    <svg
      viewBox={`0 0 ${ANCHO_ESCENA} ${ALTO_ESCENA}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ width: "100%", height: "100%", fontFamily: FUENTE_ESCENA, ...estilo }}
    >
      <Elegida inicio={inicio} cadencia={cadencia} etiquetas={etiquetas} />
    </svg>
  );
};
