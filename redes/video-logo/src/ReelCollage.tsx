import React from "react";
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { MUNDO, mezclar } from "./mundo/base";
import {
  FUENTE, NOMBRE_LOTE, SAFE_BOTTOM, SAFE_TOP, TarjetaMarca, ladoDe, normalizar, palabraClave, segmentoEn, segmentosReel, tiemposPalabras,
  type Lado, type PlanoEntrada, type PropsReel, type Segmento,
} from "./comun";

/**
 * ReelCollage — formato "recortes de papel" (aprendido del reel "Harvey, un vendedor con IA").
 *
 * Lo que tiene esa referencia, fotograma por fotograma (ver `contexto/guia-estilo-video.md` §10):
 *  - Cada paso cambia el COLOR de la pared de rayas: el corte se siente aunque la composición sea la misma.
 *  - UN objeto-metáfora grande por paso, recortado en papel: pecera = buscar clientes, tostadora = correos,
 *    embudo = seguimiento, agenda llena = reuniones. El objeto ES lo que dice la voz.
 *  - Un rótulo de cinta de enmascarar arriba con el nombre del paso.
 *  - Una mascota pequeña que reacciona (aquí: El Socio con sombrero y gafas).
 *  - Subtítulo tipo karaoke abajo: 2-3 palabras en papelitos, la palabra que suena resaltada.
 */

// ------------------------------------------------------------------ paleta de papel

const PAREDES_A = ["#4a5f7a", "#6c4a6e", "#5d5a55", "#3f5163"]; // lado A: fríos y apagados
const PAREDES_B = ["#d9a441", "#9c1c2e", "#c0643f", "#7d9a78", "#d98e8a"]; // lado B: cálidos
const PAPEL = "#f3ead7";
const CINTA = "rgba(236, 224, 196, 0.82)";
const MADERA = "#6e4326";

// ------------------------------------------------------------------ vocabulario: palabra → objeto

export const OBJETOS_COLLAGE = [
  "iman", "pecera", "diana", "clasificadora", "tostadora", "embudo", "agenda", "reloj", "papeles",
  "telefono", "etiqueta", "pantalla", "ficha", "plano", "camara", "cajas", "maquina",
] as const;
export type Objeto = (typeof OBJETOS_COLLAGE)[number];

const OBJETO_POR_PALABRA: [RegExp, Objeto][] = [
  [/se llama|presento|conoce a|te presento/, "etiqueta"],
  [/agenda|reunion|cita|calendario|agendad/, "agenda"],
  [/correo|email|mensaje a medida|propuesta|escribe/, "tostadora"],
  [/seguimiento|respuesta|responde|insiste|recordatorio/, "embudo"],
  [/separa|filtra|califica|encajan|interesad/, "clasificadora"],
  [/ideal|a quien|nicho|apunta|objetivo/, "diana"],
  [/busca|encuentra|prospect|leads|desconocid/, "pecera"],
  [/atrae|trae|llegan|clientes nuevos|mas clientes/, "iman"],
  [/audio|whatsapp|llamada|telefono|celular|nota de voz/, "telefono"],
  [/lote|devuel|entrega|pedido|caja|bodega|despacho/, "cajas"],
  [/maquina|cose|costur|confecciona/, "maquina"],
  [/ficha|medida|patron|taller|confecc|prenda|coleccion/, "ficha"],
  [/remodel|pared|obra|render|espacio|local|plano/, "plano"],
  [/foto|catalogo|producto|tienda|inventario/, "camara"],
  [/tiempo|tarde|dias|horas|semana|espera|nunca/, "reloj"],
  [/papel|manual|excel|caos|olvid|desorden|cuaderno|ciegas/, "papeles"],
  [/sistema|automat|panel|solo|inteligencia|socio/, "pantalla"],
];

const ROTULO_OBJETO: Record<Objeto, string> = {
  iman: "TRAE CLIENTES",
  pecera: "ENCUENTRA CLIENTES",
  diana: "TU CLIENTE IDEAL",
  clasificadora: "SEPARA LOS QUE ENCAJAN",
  tostadora: "CORREOS A MEDIDA",
  embudo: "SEGUIMIENTO",
  agenda: "AGENDA LLENA",
  reloj: "TIEMPO PERDIDO",
  papeles: "TODO A MANO",
  telefono: "MENSAJES SUELTOS",
  etiqueta: "TE PRESENTO",
  pantalla: "TRABAJA SOLO",
  ficha: "FICHA EXACTA",
  plano: "LO VES ANTES",
  camara: "CATÁLOGO LISTO",
  cajas: "EL PEDIDO",
  maquina: "PRODUCCIÓN",
};

/**
 * Objetos que solo existen cuando el negocio YA tiene sistema. Si la frase es del lado A
 * (el que todavía adivina), se cambian por su versión en caos: si no, pasa lo que salió en el
 * primer render real — la voz decía "el patronista adivina medidas" y en pantalla aparecía una
 * ficha exacta con el rótulo "FICHA EXACTA", justo lo contrario de lo que se está contando.
 */
const EQUIVALENTE_EN_CAOS: Partial<Record<Objeto, Objeto>> = {
  ficha: "papeles",
  agenda: "reloj",
  pantalla: "papeles",
  clasificadora: "papeles",
  tostadora: "telefono",
  plano: "papeles",
  camara: "telefono",
};

export const deducirObjeto = (texto: string, lado: Lado): Objeto => {
  const t = normalizar(texto);
  for (const [re, o] of OBJETO_POR_PALABRA) if (re.test(t)) return lado === "A" ? EQUIVALENTE_EN_CAOS[o] ?? o : o;
  return lado === "A" ? "papeles" : "pantalla";
};

type PlanoCollage = Segmento & { lado: Lado; objeto: Objeto; rotulo: string; pared: string };

export const resolverCollage = (props: PropsReel, duracionSeg: number): { planos: PlanoCollage[]; nombre: string } => {
  const { nicho, segmentos } = segmentosReel(props, duracionSeg);
  const entradas: PlanoEntrada[] = props.planos || [];
  let anterior: Objeto | null = null;
  let iA = 0;
  let iB = 0;
  const planos = segmentos.map((seg) => {
    const e = entradas[seg.indice] || {};
    const lado = ladoDe(seg, props.bloques.length, e.lado as Lado | undefined);
    let objeto = (OBJETOS_COLLAGE as readonly string[]).includes(e.objeto || "") ? (e.objeto as Objeto) : deducirObjeto(seg.texto, lado);
    if (seg.tipo === "cierre") objeto = lado === "A" ? "papeles" : "pantalla";
    if (objeto === anterior && seg.tipo === "bloque") objeto = lado === "A" ? (objeto === "reloj" ? "papeles" : "reloj") : objeto === "pantalla" ? "agenda" : "pantalla";
    anterior = objeto;
    const pared = lado === "A" ? PAREDES_A[iA++ % PAREDES_A.length] : PAREDES_B[iB++ % PAREDES_B.length];
    const rotulo = seg.tipo === "cierre"
      ? `${NOMBRE_LOTE[nicho].toUpperCase()} ${lado}`
      : (e.tooltip || "").trim().toUpperCase() || ROTULO_OBJETO[objeto];
    return { ...seg, lado, objeto, rotulo: rotulo.replace(/[0-9$%]/g, "").slice(0, 26), pared };
  });
  return { planos, nombre: NOMBRE_LOTE[nicho] };
};

// ------------------------------------------------------------------ fondo

const Pared: React.FC<{ color: string }> = ({ color }) => {
  const oscuro = mezclar(color, -0.14);
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        backgroundColor: color,
        backgroundImage: `repeating-linear-gradient(90deg, ${color} 0 62px, ${oscuro} 62px 124px)`,
      }}
    >
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 40%, rgba(255,255,255,0.10), rgba(0,0,0,0.35) 85%)" }} />
    </div>
  );
};

const Piso: React.FC = () => (
  <div style={{ position: "absolute", left: 0, right: 0, top: 1240, bottom: 0, overflow: "hidden" }}>
    <svg width={1080} height={700} style={{ position: "absolute", top: -18 }}>
      <path
        d={`M 0 30 ${Array.from({ length: 28 }).map((_, i) => `L ${i * 40 + 20} ${i % 2 ? 22 : 34}`).join(" ")} L 1080 28 L 1080 700 L 0 700 Z`}
        fill={MADERA}
      />
      <path d={`M 0 30 ${Array.from({ length: 28 }).map((_, i) => `L ${i * 40 + 20} ${i % 2 ? 22 : 34}`).join(" ")} L 1080 28`} stroke="#f0e2c4" strokeWidth={6} fill="none" />
      {[110, 230, 380, 560].map((y) => (
        <line key={y} x1={0} x2={1080} y1={y} y2={y} stroke="rgba(0,0,0,0.22)" strokeWidth={3} />
      ))}
      {[180, 520, 860, 330, 700].map((x, i) => (
        <line key={i} x1={x} x2={x} y1={i < 3 ? 110 : 230} y2={i < 3 ? 230 : 380} stroke="rgba(0,0,0,0.18)" strokeWidth={3} />
      ))}
      <rect x={0} y={0} width={1080} height={700} fill="url(#sombraPiso)" />
      <defs>
        <linearGradient id="sombraPiso" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="rgba(0,0,0,0)" />
          <stop offset="1" stopColor="rgba(0,0,0,0.45)" />
        </linearGradient>
      </defs>
    </svg>
  </div>
);

// ------------------------------------------------------------------ piezas de papel

/**
 * Recorte de papel: borde blanco + sombra dura desplazada. La sombra es una copia del mismo dibujo
 * corrida hacia abajo, NO un `filter: drop-shadow`: en este Mac el render va por swiftshader (sin GPU)
 * y cada filtro SVG a 1080x1920 cuesta cientos de milisegundos por fotograma — el formato collage
 * tardaba 18:39 contra los 13 min de los otros dos. Como la sombra no lleva desenfoque, la copia
 * desplazada se ve idéntica.
 */
/**
 * Hoja de estilo de las sombras de papel. Una regla CSS de autor gana sobre los atributos
 * `fill`/`stroke` de cada forma (los atributos de presentación tienen la especificidad más baja),
 * así que la copia de abajo sale negra entera sin tocar ni uno de los 17 objetos.
 */
export const CSS_SOMBRA_PAPEL = ".sombraPapel, .sombraPapel * { fill: #000 !important; stroke: #000 !important; }";

const Recorte: React.FC<{ children: React.ReactNode; ancho?: number; alto?: number }> = ({ children, ancho = 620, alto = 620 }) => (
  <svg width={ancho} height={alto} viewBox="0 0 600 600" style={{ overflow: "visible" }}>
    <g className="sombraPapel" transform="translate(0 14)" opacity={0.28} stroke="#000" strokeWidth={9} strokeLinejoin="round" strokeLinecap="round" paintOrder="stroke">
      {children}
    </g>
    <g stroke="#fffaf0" strokeWidth={9} strokeLinejoin="round" strokeLinecap="round" paintOrder="stroke">
      {children}
    </g>
  </svg>
);

const T: React.FC<{ x: number; y: number; s: number; children: React.ReactNode; c?: string; w?: number; anchor?: "middle" | "start" }> = ({
  x, y, s, children, c = MUNDO.tinta, w = 900, anchor = "middle",
}) => (
  <text x={x} y={y} fontSize={s} fontWeight={w} fill={c} textAnchor={anchor} dominantBaseline="central" fontFamily={FUENTE} stroke="none" letterSpacing={1}>
    {children}
  </text>
);

const Persona2D: React.FC<{ x: number; y: number; c: string; s?: number }> = ({ x, y, c, s = 1 }) => (
  <g transform={`translate(${x} ${y}) scale(${s})`}>
    <rect x={-20} y={-6} width={40} height={44} rx={12} fill={c} />
    <circle cx={0} cy={-24} r={18} fill="#e0b48c" />
    <path d="M -18 -28 A 18 18 0 0 1 18 -28 Z" fill="#2b2420" stroke="none" />
  </g>
);

const Sobre: React.FC<{ x: number; y: number; r?: number; s?: number }> = ({ x, y, r = 0, s = 1 }) => (
  <g transform={`translate(${x} ${y}) rotate(${r}) scale(${s})`}>
    <rect x={-46} y={-30} width={92} height={60} rx={6} fill="#ffffff" />
    <path d="M -46 -30 L 0 6 L 46 -30" fill="none" stroke={MUNDO.vino} strokeWidth={5} />
  </g>
);

/** Los 15 objetos-metáfora. `k` = frames desde que entró, `lado` cambia el ánimo (A roto / B funcionando). */
const ObjetoPapel: React.FC<{ objeto: Objeto; k: number; lado: Lado }> = ({ objeto, k, lado }) => {
  const sube = (desde: number) => spring({ frame: Math.max(0, k - desde), fps: 30, config: { damping: 13, stiffness: 170, mass: 0.6 } });
  const osc = Math.sin(k * 0.25);
  switch (objeto) {
    case "iman": {
      return (
        <Recorte>
          <path d="M 170 120 L 170 330 A 130 130 0 0 0 430 330 L 430 120 L 340 120 L 340 330 A 40 40 0 0 1 260 330 L 260 120 Z" fill={MUNDO.vino} />
          <rect x={170} y={100} width={90} height={70} fill="#cfd3d8" />
          <rect x={340} y={100} width={90} height={70} fill="#cfd3d8" />
          {[0, 1, 2, 3, 4].map((i) => {
            const t = sube(6 + i * 5);
            return <Persona2D key={i} x={300 + (i - 2) * 95} y={560 - t * 70 - (i % 2) * 30} c={["#3f5163", "#d9a441", "#5f7a5c", "#6c5a7d", MUNDO.vino][i]} s={0.9} />;
          })}
        </Recorte>
      );
    }
    case "pecera": {
      const pesca = sube(10);
      return (
        <Recorte>
          <ellipse cx={300} cy={340} rx={220} ry={210} fill="rgba(170,215,225,0.85)" />
          <rect x={150} y={150} width={300} height={40} rx={18} fill="rgba(200,230,235,0.95)" />
          <path d="M 95 380 Q 300 430 505 380 L 470 470 Q 300 560 130 470 Z" fill="rgba(110,170,185,0.9)" />
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <Persona2D key={i} x={190 + i * 45 + Math.sin(k * 0.12 + i) * 8} y={420 + (i % 2) * 40} c={["#3f5163", "#d9a441", "#5f7a5c", "#6c5a7d", MUNDO.vino, "#c0643f"][i]} s={0.7} />
          ))}
          <line x1={520} y1={20} x2={330} y2={260 - pesca * 40} stroke="#2f2f35" strokeWidth={4} />
          <path d={`M 330 ${260 - pesca * 40} q 0 26 -18 26`} fill="none" stroke="#2f2f35" strokeWidth={5} />
          {pesca > 0.8 ? <Persona2D x={312} y={250 - pesca * 40 + 50} c={MUNDO.vino} s={0.75} /> : null}
        </Recorte>
      );
    }
    case "diana": {
      const flecha = sube(8);
      return (
        <Recorte>
          <circle cx={300} cy={300} r={220} fill={MUNDO.vino} />
          <circle cx={300} cy={300} r={160} fill={PAPEL} />
          <circle cx={300} cy={300} r={100} fill={MUNDO.vino} />
          <circle cx={300} cy={300} r={45} fill={PAPEL} />
          <g transform={`translate(${300 + (1 - flecha) * 320} ${300 - (1 - flecha) * 220}) rotate(-35)`}>
            <rect x={0} y={-6} width={230} height={12} fill="#2f2f35" />
            <path d="M 230 -26 L 280 0 L 230 26 Z" fill="#d9a441" />
          </g>
          <line x1={240} y1={520} x2={200} y2={600} stroke="#6e4326" strokeWidth={14} />
          <line x1={360} y1={520} x2={400} y2={600} stroke="#6e4326" strokeWidth={14} />
        </Recorte>
      );
    }
    case "clasificadora": {
      const luz = Math.floor(k / 8) % 3;
      return (
        <Recorte>
          <rect x={110} y={200} width={380} height={300} rx={26} fill="#3f5c8a" />
          <rect x={150} y={150} width={300} height={90} rx={14} fill="#d9a441" />
          <rect x={170} y={240} width={260} height={80} rx={10} fill={PAPEL} />
          <T x={300} y={281} s={46}>ENCAJAN</T>
          {[0, 1, 2].map((i) => (
            <circle key={i} cx={200 + i * 100} cy={410} r={34} fill={i === luz ? ["#e05252", "#59b86b", "#f2c94c"][i] : "#2a3a55"} />
          ))}
          {[0, 1, 2].map((i) => {
            const t = ((k + i * 14) % 42) / 42;
            return (
              <g key={i} transform={`translate(${480 + 120 * (1 - t)} ${110 - 60 * Math.sin(t * Math.PI)}) rotate(${t * 40})`} opacity={t < 0.95 ? 1 : 0}>
                <rect x={-34} y={-22} width={68} height={44} rx={6} fill="#ffffff" />
                <circle cx={-14} cy={-2} r={8} fill={MUNDO.vino} stroke="none" />
              </g>
            );
          })}
        </Recorte>
      );
    }
    case "tostadora": {
      const salto = Math.max(0, Math.sin(((k % 36) / 36) * Math.PI));
      return (
        <Recorte>
          <rect x={110} y={250} width={380} height={260} rx={70} fill="#e9e5dc" />
          <rect x={170} y={235} width={100} height={24} rx={8} fill="#8e8a84" />
          <rect x={330} y={235} width={100} height={24} rx={8} fill="#8e8a84" />
          <rect x={160} y={360} width={220} height={60} rx={12} fill={MUNDO.vino} />
          <T x={270} y={391} s={30} c="#fff">EL SOCIO</T>
          <circle cx={430} cy={390} r={22} fill="#8e8a84" />
          <Sobre x={220} y={230 - salto * 130} r={-8} />
          <Sobre x={380} y={230 - Math.max(0, Math.sin((((k + 18) % 36) / 36) * Math.PI)) * 130} r={9} />
        </Recorte>
      );
    }
    case "embudo": {
      const n = Math.min(3, Math.floor(k / 12) + 1);
      return (
        <Recorte>
          <path d="M 90 120 L 510 120 L 360 360 L 360 470 L 240 470 L 240 360 Z" fill="#e05252" />
          <path d="M 135 190 L 465 190 L 420 260 L 180 260 Z" fill="#f2c94c" />
          <path d="M 205 300 L 395 300 L 370 340 L 230 340 Z" fill={PAPEL} />
          <T x={300} y={155} s={36} c="#fff">CLIENTES</T>
          <T x={300} y={225} s={30}>CHARLAS</T>
          <T x={300} y={321} s={22}>REUNIÓN</T>
          {Array.from({ length: n }).map((_, i) => (
            <circle key={i} cx={300} cy={500 + i * 34} r={14} fill={MUNDO.vino} />
          ))}
        </Recorte>
      );
    }
    case "agenda": {
      return (
        <Recorte>
          <rect x={90} y={110} width={420} height={400} rx={24} fill="#ffffff" />
          <rect x={90} y={110} width={420} height={80} rx={24} fill={MUNDO.vino} />
          <T x={300} y={151} s={38} c="#fff">AGENDA</T>
          {[0, 1, 2, 3].map((f) =>
            [0, 1, 2].map((c) => {
              const idx = f * 3 + c;
              const t = sube(6 + idx * 3);
              const llena = lado === "B" ? idx % 2 === 0 || idx === 5 : false;
              return <rect key={idx} x={115 + c * 128} y={210 + f * 72} width={114} height={58} rx={10} fill={llena ? `rgba(156,28,46,${t})` : "#f1ede6"} />;
            }),
          )}
          {lado === "B" ? (
            <g transform={`translate(420 470) rotate(-10) scale(${sube(30)})`}>
              <rect x={-110} y={-36} width={220} height={72} rx={10} fill="#d9a441" />
              <T x={0} y={1} s={34}>LLENA</T>
            </g>
          ) : null}
        </Recorte>
      );
    }
    case "reloj": {
      const vel = lado === "A" ? 0.6 : 0.08;
      return (
        <Recorte>
          <circle cx={300} cy={320} r={230} fill="#ffffff" />
          <circle cx={300} cy={320} r={200} fill={PAPEL} />
          {Array.from({ length: 12 }).map((_, i) => (
            <rect key={i} x={294} y={135} width={12} height={30} fill="#2f2f35" transform={`rotate(${i * 30} 300 320)`} />
          ))}
          <rect x={293} y={190} width={14} height={140} rx={7} fill="#2f2f35" transform={`rotate(${k * vel * 20} 300 320)`} />
          <rect x={291} y={240} width={18} height={90} rx={9} fill={MUNDO.vino} transform={`rotate(${k * vel * 2} 300 320)`} />
          <circle cx={300} cy={320} r={18} fill="#2f2f35" />
          <rect x={210} y={60} width={50} height={40} rx={8} fill="#8e8a84" />
          <rect x={340} y={60} width={50} height={40} rx={8} fill="#8e8a84" />
        </Recorte>
      );
    }
    case "papeles": {
      return (
        <Recorte>
          {Array.from({ length: 9 }).map((_, i) => {
            const t = sube(i * 2);
            const tambaleo = Math.sin(k * 0.18 + i * 0.6) * (i * 1.4);
            return (
              <g key={i} transform={`translate(${300 + tambaleo} ${530 - i * 46 * t}) rotate(${(i % 3 - 1) * 5 + tambaleo * 0.4})`}>
                <rect x={-150} y={-24} width={300} height={44} rx={4} fill={i % 2 ? "#ffffff" : "#efe8da"} />
                <line x1={-110} x2={90} y1={-2} y2={-2} stroke="#b8b2a6" strokeWidth={5} />
              </g>
            );
          })}
          {[0, 1].map((i) => (
            <g key={i} transform={`translate(${120 + i * 360 + osc * 20} ${150 + i * 60}) rotate(${osc * 25 + i * 30})`}>
              <rect x={-50} y={-36} width={100} height={72} rx={4} fill="#ffffff" />
            </g>
          ))}
        </Recorte>
      );
    }
    case "telefono": {
      return (
        <Recorte>
          <rect x={200} y={90} width={200} height={400} rx={36} fill="#2f2f35" />
          <rect x={220} y={130} width={160} height={300} rx={14} fill="#e9e5dc" />
          {[0, 1, 2].map((i) => (
            <g key={i} transform={`translate(${i % 2 ? 330 : 270} ${175 + i * 85})`} opacity={sube(4 + i * 6)}>
              <rect x={-60} y={-26} width={120} height={52} rx={26} fill={i % 2 ? "#f8e9ec" : "#ffffff"} />
              <circle cx={-34} cy={0} r={10} fill={MUNDO.vino} />
              {[0, 1, 2, 3, 4].map((b) => (
                <rect key={b} x={-16 + b * 12} y={-((b * 7 + i * 3) % 14) - 4} width={6} height={((b * 7 + i * 3) % 14) * 2 + 8} rx={3} fill="#6e6e73" />
              ))}
            </g>
          ))}
          {lado === "A"
            ? [0, 1].map((i) => <path key={i} d={`M ${430 + i * 30} ${150 - i * 10} a ${60 + i * 40} ${60 + i * 40} 0 0 1 0 ${120 + i * 50}`} fill="none" stroke="#e05252" strokeWidth={10} opacity={0.5 + 0.5 * Math.sin(k * 0.5)} />)
            : null}
        </Recorte>
      );
    }
    case "etiqueta": {
      const letras = Math.min(8, Math.floor(k / 3));
      return (
        <Recorte>
          <rect x={60} y={150} width={480} height={330} rx={30} fill={MUNDO.vino} />
          <T x={300} y={215} s={64} c="#fff">HOLA</T>
          <T x={300} y={265} s={24} c="#fff" w={800}>ME LLAMO</T>
          <rect x={95} y={300} width={410} height={150} rx={12} fill="#ffffff" />
          <T x={300} y={378} s={70}>{"EL SOCIO".slice(0, letras)}</T>
        </Recorte>
      );
    }
    case "pantalla": {
      return (
        <Recorte>
          <rect x={70} y={110} width={460} height={330} rx={24} fill="#1f1f24" />
          <rect x={95} y={135} width={410} height={280} rx={10} fill="#2b2b33" />
          {["CLIENTES", "CORREOS", "RESPUESTAS", "REUNIONES"].map((t, i) => {
            const w = 360 * Math.min(1, sube(6 + i * 5)) * (1 - i * 0.18);
            return (
              <g key={t}>
                <rect x={120 + (360 - w) / 2} y={160 + i * 62} width={w} height={46} rx={8} fill={["#e05252", "#d9a441", "#f2c94c", "#7d9a78"][i]} />
                <T x={300} y={183 + i * 62} s={22} c="#1f1f24">{t}</T>
              </g>
            );
          })}
          <rect x={250} y={440} width={100} height={60} fill="#8e8a84" />
          <rect x={180} y={495} width={240} height={24} rx={8} fill="#8e8a84" />
          <g transform="translate(470 120) rotate(8)">
            <rect x={-70} y={-24} width={140} height={48} rx={8} fill={MUNDO.vino} />
            <T x={0} y={1} s={24} c="#fff">EN VIVO</T>
          </g>
        </Recorte>
      );
    }
    case "ficha": {
      return (
        <Recorte>
          <rect x={110} y={70} width={380} height={470} rx={16} fill="#ffffff" />
          <T x={300} y={115} s={30}>FICHA TÉCNICA</T>
          <path d="M 200 170 L 250 155 Q 300 185 350 155 L 400 170 L 440 225 L 400 245 L 390 225 L 390 380 L 210 380 L 210 225 L 200 245 L 160 225 Z" fill={lado === "A" ? "#e9e5dc" : "#f3ece0"} stroke="#2f2f35" strokeWidth={5} />
          {lado === "B" ? (
            <>
              <line x1={210} y1={400} x2={390} y2={400} stroke={MUNDO.vino} strokeWidth={6} />
              <line x1={420} y1={245} x2={420} y2={380} stroke={MUNDO.vino} strokeWidth={6} />
              {[440, 480].map((y, i) => (
                <g key={y} opacity={sube(8 + i * 6)}>
                  <rect x={150} y={y - 14} width={250} height={26} rx={6} fill="#f1ede6" />
                  <T x={430} y={y} s={34} c={MUNDO.vino}>✓</T>
                </g>
              ))}
            </>
          ) : (
            <T x={300} y={460} s={120} c={MUNDO.vino}>?</T>
          )}
        </Recorte>
      );
    }
    case "plano": {
      const color = sube(10);
      return (
        <Recorte>
          <rect x={60} y={90} width={480} height={420} rx={14} fill="#3f5f80" />
          {[150, 210, 270, 330, 390, 450].map((y) => (
            <line key={y} x1={80} x2={520} y1={y} y2={y} stroke="rgba(255,255,255,0.15)" strokeWidth={3} />
          ))}
          <path d="M 170 300 L 300 190 L 430 300 L 430 450 L 170 450 Z" fill={lado === "B" ? `rgba(243,234,215,${color})` : "none"} stroke="#ffffff" strokeWidth={8} />
          <rect x={270} y={360} width={60} height={90} fill={lado === "B" ? MUNDO.vino : "none"} stroke="#ffffff" strokeWidth={6} />
          <rect x={200} y={320} width={50} height={46} fill={lado === "B" ? "#9fb0bb" : "none"} stroke="#ffffff" strokeWidth={6} />
          <rect x={350} y={320} width={50} height={46} fill={lado === "B" ? "#9fb0bb" : "none"} stroke="#ffffff" strokeWidth={6} />
          {lado === "A" ? <T x={300} y={140} s={40} c="#f2c94c">¿Y SI NO QUEDA?</T> : <T x={300} y={140} s={40} c="#fff">RENDER</T>}
        </Recorte>
      );
    }
    case "cajas": {
      const listo = lado === "B";
      return (
        <Recorte>
          {[[110, 330], [300, 330], [205, 170], [395, 170], [490, 330]].slice(0, listo ? 5 : 4).map(([x, y], i) => {
            const t = sube(i * 4);
            const caida = listo ? 0 : Math.sin(k * 0.15 + i) * 4;
            return (
              <g key={i} transform={`translate(${x} ${Number(y) + (1 - t) * -200}) rotate(${listo ? 0 : (i % 2 ? 7 : -6) + caida})`}>
                <rect x={-90} y={0} width={180} height={150} rx={8} fill="#c9a77c" />
                <rect x={-14} y={0} width={28} height={150} fill="#e6d3ad" stroke="none" />
                <g transform="rotate(-8)">
                  <rect x={-74} y={56} width={148} height={40} rx={6} fill={listo ? MUNDO.vino : "#e05252"} />
                  <T x={0} y={77} s={24} c="#fff">{listo ? "LISTO ✓" : "DEVUELTO"}</T>
                </g>
              </g>
            );
          })}
        </Recorte>
      );
    }
    case "maquina": {
      const aguja = Math.abs(Math.sin(k * 0.9)) * 18;
      return (
        <Recorte>
          <rect x={60} y={430} width={480} height={50} rx={10} fill="#a5713f" />
          <rect x={110} y={350} width={380} height={80} rx={16} fill="#f1ede4" />
          <rect x={390} y={170} width={90} height={190} rx={18} fill="#f1ede4" />
          <rect x={130} y={150} width={350} height={90} rx={30} fill="#f1ede4" />
          <rect x={150} y={238 + aguja} width={22} height={70 - aguja} rx={6} fill="#8e8a84" />
          <rect x={250} y={180} width={130} height={30} rx={8} fill={MUNDO.vino} />
          <circle cx={460} cy={240} r={34} fill="#cfcac0" />
          <path d={`M 40 420 Q 160 ${400 - aguja} 300 420 T 560 420`} fill="none" stroke={lado === "B" ? MUNDO.vino : "#8e8a84"} strokeWidth={10} />
          {lado === "B" ? (
            <g transform={`translate(470 110) scale(${sube(10)})`}>
              <circle r={44} fill="#7d9a78" />
              <T x={0} y={2} s={50} c="#fff">✓</T>
            </g>
          ) : (
            <T x={470} y={110} s={110} c="#e05252">?</T>
          )}
        </Recorte>
      );
    }
    case "camara":
    default: {
      const flash = lado === "A" ? k % 30 < 4 : false;
      return (
        <Recorte>
          <rect x={90} y={200} width={420} height={280} rx={36} fill="#2f2f35" />
          <rect x={150} y={160} width={140} height={60} rx={14} fill="#2f2f35" />
          <circle cx={300} cy={340} r={110} fill="#4a4a52" />
          <circle cx={300} cy={340} r={75} fill="#1c1c20" />
          <circle cx={275} cy={315} r={20} fill="rgba(255,255,255,0.4)" stroke="none" />
          <rect x={410} y={225} width={60} height={34} rx={8} fill={flash ? "#ffffff" : "#d9a441"} />
          {flash ? <circle cx={440} cy={242} r={110} fill="rgba(255,255,255,0.8)" stroke="none" /> : null}
          {lado === "B"
            ? [0, 1, 2].map((i) => (
                <g key={i} transform={`translate(${170 + i * 130} ${540}) scale(${sube(6 + i * 4)})`}>
                  <rect x={-50} y={-40} width={100} height={80} rx={10} fill="#ffffff" />
                  <rect x={-22} y={-26} width={44} height={52} rx={6} fill={[MUNDO.vino, "#d9a441", "#6c5a7d"][i]} />
                </g>
              ))
            : null}
        </Recorte>
      );
    }
  }
};

// ------------------------------------------------------------------ mascota: El Socio en papel

const Mascota: React.FC<{ frame: number; lado: Lado; k: number }> = ({ frame, lado, k }) => {
  const feliz = lado === "B";
  const brinco = feliz ? Math.abs(Math.sin(frame * 0.18)) * 14 : Math.abs(Math.sin(frame * 0.07)) * 3;
  const brazo = feliz ? Math.sin(frame * 0.4) * 30 - 40 : 20;
  const entra = spring({ frame: k, fps: 30, config: { damping: 12, stiffness: 160 } });
  // Mismo truco de sombra que `Recorte`: copia negra desplazada en vez de `filter: drop-shadow`.
  const cuerpo = (
    <>
      <g stroke="#fffaf0" strokeWidth={7} strokeLinejoin="round" paintOrder="stroke">
        <rect x={60} y={175} width={30} height={60} rx={10} fill="#2f2f35" />
        <rect x={130} y={175} width={30} height={60} rx={10} fill="#2f2f35" />
        <g transform={`rotate(${brazo} 175 160)`}>
          <rect x={165} y={150} width={26} height={74} rx={13} fill={MUNDO.vino} />
        </g>
        <rect x={38} y={150} width={26} height={70} rx={13} fill={MUNDO.vino} />
        <rect x={55} y={120} width={120} height={95} rx={26} fill={MUNDO.vino} />
        <path d="M 115 122 L 95 165 L 115 190 L 135 165 Z" fill={PAPEL} />
        <rect x={50} y={36} width={130} height={100} rx={28} fill="#e8c39e" />
        <rect x={74} y={-10} width={82} height={50} rx={6} fill="#1c1c20" />
        <rect x={74} y={26} width={82} height={10} fill={MUNDO.vino} stroke="none" />
        <ellipse cx={115} cy={40} rx={70} ry={11} fill="#1c1c20" />
      </g>
      <circle cx={92} cy={82} r={17} fill="none" stroke="#1c1c20" strokeWidth={6} />
      <circle cx={138} cy={82} r={17} fill="none" stroke="#1c1c20" strokeWidth={6} />
      <path d="M 109 80 Q 115 74 121 80" stroke="#1c1c20" strokeWidth={5} fill="none" />
      <circle cx={92} cy={83} r={5} fill="#1c1c20" />
      <circle cx={138} cy={83} r={5} fill="#1c1c20" />
      <path d={feliz ? "M 96 110 Q 115 126 134 110" : "M 98 118 Q 115 108 132 118"} stroke="#1c1c20" strokeWidth={6} fill="none" strokeLinecap="round" />
    </>
  );
  return (
    <svg width={230} height={290} viewBox="0 0 230 290" style={{ overflow: "visible", transform: `translateY(${-brinco}px) scale(${0.92 + 0.08 * entra})` }}>
      <g className="sombraPapel" transform="translate(0 10)" opacity={0.28}>
        {cuerpo}
      </g>
      {cuerpo}
    </svg>
  );
};

// ------------------------------------------------------------------ rótulo, contador, karaoke

const Rotulo: React.FC<{ texto: string; k: number; grande?: boolean }> = ({ texto, k, grande = false }) => {
  const e = spring({ frame: k, fps: 30, config: { damping: 14, stiffness: 190, mass: 0.6 } });
  const palabras = texto.split(/\s+/);
  const clave = palabraClave(palabras);
  return (
    <div style={{ position: "relative", transform: `rotate(-1.6deg) translateY(${(1 - e) * -60}px)`, opacity: Math.min(1, e * 1.5), maxWidth: 820 }}>
      <div
        style={{
          backgroundColor: PAPEL,
          padding: grande ? "26px 34px 30px" : "18px 34px 20px",
          boxShadow: "0 10px 0 rgba(0,0,0,0.25)",
          fontFamily: FUENTE,
          fontWeight: 900,
          fontSize: grande ? 64 : 46,
          letterSpacing: "0.02em",
          lineHeight: 1.08,
          color: MUNDO.tinta,
          textAlign: "center",
          clipPath: "polygon(0% 4%, 3% 0%, 50% 2%, 97% 0%, 100% 5%, 99% 50%, 100% 96%, 96% 100%, 50% 98%, 3% 100%, 0% 95%, 1% 50%)",
        }}
      >
        {palabras.map((p, i) => (
          <span key={i} style={{ display: "inline-block", margin: "0 0.12em", ...(grande && i === clave ? { backgroundColor: MUNDO.vino, color: "#fff", padding: "0 0.18em" } : {}) }}>
            {p}
          </span>
        ))}
      </div>
      <div style={{ position: "absolute", left: -20, top: -14, width: 110, height: 40, backgroundColor: CINTA, transform: "rotate(-24deg)" }} />
      <div style={{ position: "absolute", right: -20, top: -14, width: 110, height: 40, backgroundColor: CINTA, transform: "rotate(22deg)" }} />
    </div>
  );
};

const Contador: React.FC<{ lado: Lado; llenos: number; k: number }> = ({ lado, llenos, k }) => {
  const e = spring({ frame: Math.max(0, k - 6), fps: 30, config: { damping: 14, stiffness: 180 } });
  return (
    <div style={{ backgroundColor: PAPEL, padding: "14px 20px", transform: `rotate(3deg) scale(${e})`, boxShadow: "0 8px 0 rgba(0,0,0,0.25)", fontFamily: FUENTE }}>
      <div style={{ fontSize: 20, fontWeight: 900, letterSpacing: "0.12em", color: "#5a544b" }}>{lado === "A" ? "SIN RESPUESTA" : "CLIENTES"}</div>
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        {[0, 1, 2, 3, 4].map((i) => (
          <div
            key={i}
            style={{
              width: 24,
              height: 24,
              borderRadius: 12,
              backgroundColor: i < llenos ? (lado === "A" ? "#8e8a84" : MUNDO.vino) : "transparent",
              border: `3px solid ${lado === "A" ? "#8e8a84" : MUNDO.vino}`,
            }}
          />
        ))}
      </div>
    </div>
  );
};

const Karaoke: React.FC<{ texto: string; inicio: number; fin: number; seg: number; fps: number }> = ({ texto, inicio, fin, seg, fps }) => {
  const palabras = texto.split(/\s+/).filter(Boolean);
  if (!palabras.length) return null;
  // La frase entera se lee en pantalla (como en el formato mundo) y el recorte rojo viaja
  // palabra por palabra siguiendo la voz. Antes solo se veían 3 palabras sueltas: nadie
  // alcanzaba a leer la frase completa.
  const f0 = Math.round(inicio * fps);
  const f1 = Math.round(fin * fps);
  const voz = tiemposPalabras(palabras, f0, f1 - Math.min(12, (f1 - f0) * 0.12));
  const frame = seg * fps;
  let hablando = -1;
  for (let k = 0; k < voz.length; k++) if (frame >= voz[k]) hablando = k;
  const fontSize = texto.length <= 34 ? 58 : texto.length <= 58 ? 52 : 46;
  return (
    <div style={{ display: "flex", gap: 10, justifyContent: "center", flexWrap: "wrap" }}>
      {palabras.map((p, i) => {
        const esActual = i === hablando;
        const entra = interpolate(frame, [voz[i] - 5, voz[i] + 2], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
        return (
          <span
            key={`${i}-${p}`}
            style={{
              fontFamily: FUENTE,
              fontWeight: 900,
              fontSize,
              padding: "5px 14px 8px",
              backgroundColor: esActual ? MUNDO.vino : PAPEL,
              color: esActual ? "#fff" : MUNDO.tinta,
              opacity: 0.45 + entra * 0.55,
              transform: `rotate(${(i % 2 ? 1.5 : -1.5).toFixed(1)}deg) scale(${esActual ? 1.06 : 1})`,
              boxShadow: "0 5px 0 rgba(0,0,0,0.3)",
            }}
          >
            {p}
          </span>
        );
      })}
    </div>
  );
};

// ------------------------------------------------------------------ componente

export const ReelCollage: React.FC<PropsReel> = (props) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const seg = frame / fps;
  const { planos } = resolverCollage(props, durationInFrames / fps);
  const i = segmentoEn(planos, seg);
  const p = planos[i];
  const prev = i > 0 ? planos[i - 1] : null;
  const k = frame - Math.round(p.inicio * fps);

  // Cambio de pared: la nueva entra deslizando desde la derecha en 7 frames (como pasar una página).
  const barrido = prev ? interpolate(k, [0, 7], [1080, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) }) : 0;
  const kObjeto = p.tipo === "gancho" ? k + 14 : k; // en el gancho el objeto ya está en el primer fotograma
  const objetoEntra = spring({ frame: Math.max(0, kObjeto - 3), fps, config: { damping: 11, stiffness: 150, mass: 0.7 } });
  const flota = Math.sin(frame * 0.09) * 8;
  const llenos = planos.slice(0, i + 1).filter((x) => x.lado === p.lado && x.tipo !== "gancho").length;

  return (
    <AbsoluteFill style={{ backgroundColor: "#222", overflow: "hidden" }}>
      <style>{CSS_SOMBRA_PAPEL}</style>
      {prev ? <Pared color={prev.pared} /> : null}
      <div style={{ position: "absolute", inset: 0, transform: `translateX(${barrido}px)` }}>
        <Pared color={p.pared} />
      </div>
      <Piso />

      {/* Rótulo de cinta: el gancho va completo y grande desde el primer fotograma */}
      <div style={{ position: "absolute", top: SAFE_TOP + 20, left: 0, right: 0, display: "flex", justifyContent: "center" }}>
        <Rotulo key={`r${i}`} texto={p.tipo === "gancho" ? p.texto.toUpperCase() : p.rotulo} k={p.tipo === "gancho" ? Math.max(k, 12) : k} grande={p.tipo === "gancho"} />
      </div>

      {p.tipo !== "gancho" && !p.final ? (
        <div style={{ position: "absolute", top: SAFE_TOP + 150, right: 175 }}>
          <Contador key={`c${i}`} lado={p.lado} llenos={Math.min(5, llenos)} k={k} />
        </div>
      ) : null}

      {/* Objeto-metáfora: lo que dice la voz, recortado en papel */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: p.tipo === "gancho" ? 640 : 560,
          display: "flex",
          justifyContent: "center",
          transform: `translateY(${((1 - objetoEntra) * 260 + flota).toFixed(1)}px) rotate(${((1 - objetoEntra) * -10).toFixed(2)}deg) scale(${(1.16 * (0.6 + 0.4 * objetoEntra)).toFixed(3)})`,
          opacity: Math.min(1, objetoEntra * 2),
        }}
      >
        <ObjetoPapel key={`o${i}`} objeto={p.objeto} k={kObjeto} lado={p.lado} />
      </div>

      <div style={{ position: "absolute", right: 150, top: 1090, transform: "scale(1.3)", transformOrigin: "bottom right" }}>
        <Mascota frame={frame} lado={p.lado} k={k} />
      </div>

      {p.tipo !== "gancho" && !p.final ? (
        <div style={{ position: "absolute", left: 50, right: 50, bottom: SAFE_BOTTOM + 60 }}>
          <Karaoke texto={p.texto} inicio={p.inicio} fin={p.fin} seg={seg} fps={fps} />
        </div>
      ) : null}

      {p.final ? <TarjetaMarca frameLocal={k} fps={fps} texto={p.texto} /> : null}
    </AbsoluteFill>
  );
};

/** Para la ficha de la composición. */
export const ladoCollage = (s: Segmento, n: number) => ladoDe(s, n);
