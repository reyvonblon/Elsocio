import React from "react";
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { MUNDO } from "./mundo/base";
import {
  FUENTE, NOMBRE_LOTE, SAFE_TOP, TarjetaMarca, Titular, ladoDe, normalizar, segmentoEn, segmentosReel,
  type Lado, type PlanoEntrada, type PropsReel, type Segmento,
} from "./comun";
import type { NombreNicho } from "./mundo/interiores";

/**
 * ReelDuelo — pantalla partida A vs B (aprendido del reel "Novato vs Pro", ver guía §11).
 *
 * Mecánica de la referencia, fotograma por fotograma:
 *  - La pantalla se parte en dos con una línea brillante y una moneda "VS" en el centro.
 *  - Arriba el que lo hace mal, abajo el que lo hace bien. Cada frase actualiza SOLO la mitad de la que habla;
 *    la otra se apaga un poco para que el ojo sepa dónde mirar.
 *  - Cada mitad tiene una ventana de app (lo que pasa) y un medidor grande a la derecha (cómo va).
 *    La referencia usa cifras ("-40 créditos", "0 ventas"); El Socio no dice cifras, así que el medidor
 *    es un anillo que se vacía (A) o se llena (B), con una etiqueta de estado.
 *  - En el gancho las dos ventanas reciben el MISMO encargo; después, mientras el lado B no ha
 *    hablado, su ventana espera con el encargo quieto. Eso genera la tensión.
 */

export const PANELES_DUELO = ["chat", "papeles", "bandeja", "reloj", "cajas", "ficha", "agenda", "catalogo", "render", "correo", "maquina"] as const;
type Panel = (typeof PANELES_DUELO)[number];

/**
 * Paneles que tienen sentido en cada nicho, por lado. Antes no existía esta lista: las 12 reglas
 * de palabras valían para los cuatro negocios y el que no encajaba caía en papeles/correo. Medido
 * sobre los 6 guiones reales: 39% de los planos acababan en esos dos, y 14 de 41 repetían el panel
 * anterior (tres "correo" seguidos en el reel de la agencia).
 */
const PANEL_POR_NICHO: Record<NombreNicho, Record<Lado, Panel[]>> = {
  taller: { A: ["papeles", "cajas", "chat", "reloj", "maquina"], B: ["ficha", "maquina", "cajas", "catalogo"] },
  obra: { A: ["papeles", "reloj", "chat", "render"], B: ["render", "catalogo", "ficha", "agenda"] },
  estudio: { A: ["cajas", "papeles", "chat", "reloj"], B: ["catalogo", "cajas", "render", "agenda"] },
  oficina: { A: ["papeles", "bandeja", "chat", "reloj", "cajas"], B: ["correo", "agenda", "bandeja", "catalogo"] },
};

/** Palabras propias del nicho; se consultan antes que las generales de abajo. */
const PANEL_POR_NICHO_PALABRA: Record<NombreNicho, [RegExp, Panel, Panel][]> = {
  taller: [
    [/ficha|medida|patron|talle|ajustad|acabado|especific|exact/, "papeles", "ficha"],
    [/cose|costur|confeccion|maquina|produccion|puntada/, "maquina", "maquina"],
    [/lote|pedido|entrega|devuel|caja|despacho|prenda|coleccion|tela/, "cajas", "cajas"],
    [/audio|whatsapp|nota de voz|mensaje|celular/, "chat", "correo"],
    [/adivina|interpreta|a su manera|a mano|papel|cuaderno|ciegas|duda/, "papeles", "ficha"],
    [/semana|dias|reproceso|espera|rehacer|otra vez|tarde/, "reloj", "agenda"],
  ],
  obra: [
    [/render|plano|espacio|remodel|obra|terminado|ves|visto|antes de/, "render", "render"],
    [/pared|ladrillo|meson|mueble|piso|color|luz|tumbar|romper|andamio/, "render", "render"],
    [/muestra|material|referencia|catalogo|acabado/, "papeles", "catalogo"],
    [/pantalla|sistema|ajusta|panel|socio/, "papeles", "render"],
    [/imagina|ciegas|a mano|papel|sorpresa|reproceso|chiquita/, "papeles", "ficha"],
    [/semana|dias|espera|volver a|otra vez|tarde/, "reloj", "agenda"],
  ],
  estudio: [
    [/semana|dias|espera|demora|tarde|nunca|lanzamiento/, "reloj", "agenda"],
    [/catalogo|publica|tienda|vende|mira|nadie|producto|articulo/, "cajas", "catalogo"],
    [/foto|sesion|luz|imagen|estudio|camara/, "cajas", "catalogo"],
    [/inventario|bodega|stock|despacho|pedido|lote|caja|mueve/, "cajas", "cajas"],
    [/celular|whatsapp|audio|llamada/, "chat", "correo"],
    [/prestad|afan|a mano|papel|distinta/, "papeles", "ficha"],
  ],
  oficina: [
    [/agenda|reunion|cita|calendario|agendad/, "reloj", "agenda"],
    [/correo|email|bandeja|propuesta|escribe|responde|respuesta|seguimiento/, "bandeja", "correo"],
    [/excel|celda|copia|pega|formulario|reporte|informe|dato|manual|papel|a mano/, "papeles", "correo"],
    [/filtra|separa|califica|prospecto|lead|cliente|encajan/, "bandeja", "correo"],
    [/hora|tarde|dias|semana|espera|reproceso|quinta vez|no vuelven/, "reloj", "agenda"],
    [/audio|whatsapp|llamada|mensaje|celular/, "chat", "correo"],
    [/sistema|automat|panel|herramienta|socio|listo|solo/, "papeles", "catalogo"],
  ],
};

const PANEL_POR_PALABRA: [RegExp, Panel, Panel][] = [
  // [palabras, panel si es lado A, panel si es lado B]. Gana la primera que aparezca en la frase.
  [/audio|whatsapp|nota de voz/, "chat", "correo"],
  // "Las máquinas cosen" tiene que mostrar máquinas: antes caía en /adivina/ y salía una ficha.
  [/maquina|cose|costur|confecciona|produccion/, "maquina", "maquina"],
  [/lote|devuel|caja|bodega|pedido/, "cajas", "cajas"],
  [/agenda|reunion|cita|calendario|agendad/, "reloj", "agenda"],
  [/ficha|medida|patron|especific/, "papeles", "ficha"],
  [/render|remodel|pared|obra|plano|espacio|sala/, "render", "render"],
  [/catalogo|foto|producto|tienda|publica/, "cajas", "catalogo"],
  [/correo|bandeja|email|responde|respuesta|seguimiento|cliente/, "bandeja", "correo"],
  [/mensaje/, "chat", "correo"],
  [/inventario/, "cajas", "catalogo"],
  [/tiempo|tarde|dias|horas|espera|nunca|nadie/, "reloj", "agenda"],
  [/papel|manual|excel|cuaderno|desorden|adivina|ciegas|interpreta/, "papeles", "ficha"],
];

/** El estado de cada ventana habla del NEGOCIO, no del embudo de ventas: "AGENDADO" no dice nada
 *  en un reel de catálogo. Son los mismos cuatro turnos, pero contados en el idioma del nicho. */
const ESTADOS: Record<NombreNicho, Record<Lado, string[]>> = {
  taller: { A: ["A OJO", "LOTE DEVUELTO", "SIN FICHA", "REPROCESO"], B: ["MEDIDA EXACTA", "LOTE LISTO", "SIN DUDAS", "A LA PRIMERA"] },
  obra: { A: ["A CIEGAS", "HAY QUE TUMBAR", "SIN VERLO", "REPROCESO"], B: ["LO VES ANTES", "SIN SORPRESAS", "APROBADO", "TAL CUAL"] },
  estudio: { A: ["NADIE LO MIRA", "FOTO DISTINTA", "SEMANAS", "SIN PUBLICAR"], B: ["SE VENDE SOLO", "CATÁLOGO LISTO", "SIN MOVER NADA", "PUBLICADO"] },
  oficina: { A: ["SIN RESPUESTA", "TODO A MANO", "HORAS PERDIDAS", "ATRASADO"], B: ["RESPONDIDO", "AGENDADO", "EN MARCHA", "AUTOMÁTICO"] },
};

type PlanoDuelo = Segmento & { lado: Lado; panel: Panel; estado: string };

export const resolverDuelo = (props: PropsReel, duracionSeg: number) => {
  const { nicho, segmentos } = segmentosReel(props, duracionSeg);
  const entradas: PlanoEntrada[] = props.planos || [];
  let iA = 0;
  let iB = 0;
  let anterior: Panel | null = null;
  let ladoAnterior: Lado | null = null;
  const planos: PlanoDuelo[] = segmentos.map((seg) => {
    const e = entradas[seg.indice] || {};
    const lado = ladoDe(seg, props.bloques.length, e.lado as Lado | undefined);
    const t = normalizar(seg.texto);
    // Todo lo que la frase sugiere, en orden: primero el nicho, luego las reglas generales y por
    // último los paneles del nicho. Tener la lista (y no un solo valor) permite resolver una
    // repetición con lo que dice la propia frase en vez de dejar tres "correo" seguidos.
    const candidatos: Panel[] = [];
    const empujar = (x: Panel) => { if (!candidatos.includes(x)) candidatos.push(x); };
    const porTarjeta: Record<string, Panel> = { correo: "correo", agenda: "agenda", ficha: "ficha", catalogo: "catalogo", render: "render", chat: "chat" };
    if (e.tarjeta && porTarjeta[e.tarjeta]) empujar(porTarjeta[e.tarjeta]);
    for (const [re, a, b] of PANEL_POR_NICHO_PALABRA[nicho]) if (re.test(t)) empujar(lado === "A" ? a : b);
    for (const [re, a, b] of PANEL_POR_PALABRA) if (re.test(t)) empujar(lado === "A" ? a : b);
    for (const x of PANEL_POR_NICHO[nicho][lado]) empujar(x);
    let panel = candidatos[0];
    // Solo se evita la repetición DENTRO del mismo lado: ver el mismo encargo en la ventana A y
    // luego en la B es la mecánica del duelo, no un defecto, y forzar un cambio ahí rompía la
    // frase ("ves el espacio terminado" acababa en un catálogo en vez de en el render).
    if (panel === anterior && ladoAnterior === lado && seg.tipo !== "cierre") {
      panel = candidatos.find((x) => x !== anterior) ?? panel;
    }
    anterior = panel;
    ladoAnterior = lado;
    const turnos = ESTADOS[nicho][lado];
    const estado = ((e.tooltip || "").trim() || turnos[(lado === "A" ? iA : iB) % turnos.length])
      .toUpperCase().replace(/[0-9$%]/g, "").slice(0, 18);
    if (seg.tipo === "bloque") lado === "A" ? iA++ : iB++;
    return { ...seg, lado, panel, estado };
  });
  return { planos, nombre: NOMBRE_LOTE[nicho] };
};

// ------------------------------------------------------------------ contenido de las ventanas

const Fila: React.FC<{ y: number; activa?: boolean; check?: boolean; punto?: boolean; ancho?: number }> = ({ y, activa, check, punto, ancho = 300 }) => (
  <g>
    <rect x={24} y={y} width={492} height={48} rx={10} fill={activa ? "#f0dad9" : "#e4ddce"} stroke={activa ? MUNDO.vino : "none"} strokeWidth={2} />
    <circle cx={50} cy={y + 24} r={12} fill={punto ? "#b2283a" : "#b4aca0"} />
    <rect x={74} y={y + 14} width={ancho} height={10} rx={5} fill="#a8a096" />
    <rect x={74} y={y + 30} width={ancho * 0.6} height={8} rx={4} fill="#bdb5a8" />
    {check ? <text x={490} y={y + 26} fontSize={28} fill={MUNDO.vinoClaro} fontWeight={900} textAnchor="middle" dominantBaseline="central">✓</text> : null}
  </g>
);

const ContenidoPanel: React.FC<{ panel: Panel; k: number; lado: Lado; paso?: number }> = ({ panel, k, lado, paso = 1 }) => {
  // `paso` estira el escalonado de entrada. En el gancho vale más de 1 para que el encargo siga
  // llegando durante toda la frase: con paso 1 el panel se armaba en medio segundo y el resto del
  // gancho quedaba congelado (3.5 s quietos en el primer render real).
  const s = (d: number) => spring({ frame: Math.max(0, k - d * paso), fps: 30, config: { damping: 15, stiffness: 190 } });
  const fuente = { fontFamily: FUENTE, fontWeight: 800 } as const;
  switch (panel) {
    case "chat":
      return (
        <g>
          {[0, 1, 2].map((i) => (
            <g key={i} transform={`translate(${i % 2 ? 250 : 30} ${30 + i * 70})`} opacity={s(i * 5)}>
              <rect width={250} height={52} rx={26} fill={i % 2 ? "#f0dad9" : "#dcd4c4"} />
              <circle cx={28} cy={26} r={11} fill={MUNDO.vino} />
              {Array.from({ length: 14 }).map((_, b) => {
                const h = 6 + ((b * 7 + i * 5) % 22);
                return <rect key={b} x={50 + b * 13} y={26 - h / 2} width={6} height={h} rx={3} fill="#8d857a" />;
              })}
            </g>
          ))}
          <g transform="translate(30 240)" opacity={s(18)}>
            <rect width={300} height={46} rx={23} fill="#dcd4c4" />
            <text x={150} y={24} fontSize={22} fill={MUNDO.tinta} textAnchor="middle" dominantBaseline="central" style={fuente}>¿así o más ajustado?</text>
          </g>
        </g>
      );
    case "papeles":
      return (
        <g>
          {Array.from({ length: 7 }).map((_, i) => {
            const t = s(i * 2);
            const w = Math.sin(k * 0.2 + i) * i * 1.2;
            return (
              <g key={i} transform={`translate(${270 + w} ${270 - i * 30 * t}) rotate(${(i % 3 - 1) * 4 + w * 0.5})`}>
                <rect x={-130} y={-14} width={260} height={28} rx={3} fill={i % 2 ? "#e9e5dc" : "#d6d0c4"} />
              </g>
            );
          })}
          {[[70, 60, "#f2d36b"], [420, 90, "#f3a9a0"], [400, 200, "#f2d36b"]].map(([x, y, c], i) => (
            <rect key={i} x={Number(x)} y={Number(y)} width={70} height={60} fill={String(c)} transform={`rotate(${(i - 1) * 9} ${Number(x) + 35} ${Number(y) + 30})`} opacity={s(10 + i * 4)} />
          ))}
        </g>
      );
    case "bandeja":
      return (
        <g>
          {[0, 1, 2, 3, 4].map((i) => (
            <g key={i} opacity={s(i * 3)}>
              <Fila y={20 + i * 56} punto activa={i === 0} ancho={240 + (i % 2) * 60} />
            </g>
          ))}
        </g>
      );
    case "correo":
      return (
        <g>
          {[0, 1, 2, 3].map((i) => (
            <g key={i} opacity={s(i * 4)}>
              <Fila y={24 + i * 66} check activa={i === 0} ancho={260} />
            </g>
          ))}
          {[0, 1, 2].map((i) => {
            const c = ((k + i * 16) % 48) / 48;
            return (
              <g key={`s${i}`} transform={`translate(${520 - c * 480} ${18 + Math.sin(c * Math.PI) * -10})`} opacity={c < 0.9 ? 1 : 0}>
                <rect x={-18} y={-12} width={36} height={24} rx={3} fill="#fff" />
                <path d="M -18 -12 L 0 2 L 18 -12" stroke={MUNDO.vino} strokeWidth={2} fill="none" />
              </g>
            );
          })}
        </g>
      );
    case "reloj": {
      const vel = lado === "A" ? 14 : 2;
      return (
        <g transform="translate(270 160)">
          <circle r={120} fill="#7d7266" />
          <circle r={104} fill="#f3ece0" />
          {Array.from({ length: 12 }).map((_, i) => (
            <rect key={i} x={-3} y={-98} width={6} height={16} fill="#8d857a" transform={`rotate(${i * 30})`} />
          ))}
          <rect x={-4} y={-80} width={8} height={80} rx={4} fill={MUNDO.tinta} transform={`rotate(${k * vel})`} />
          <rect x={-5} y={-55} width={10} height={55} rx={5} fill={MUNDO.vinoClaro} transform={`rotate(${k * vel * 0.08})`} />
          <circle r={9} fill={MUNDO.tinta} />
        </g>
      );
    }
    case "cajas":
      return (
        <g>
          {/* La fila de abajo llegaba a y=318 dentro de un panel que recorta en 300: las cajas
              salían partidas por el borde. Con +20 la pirámide entera cabe (10 → 278). */}
          {[[90, 170], [220, 170], [350, 170], [150, 80], [290, 80], [220, -10]].map(([x, y], i) => (
            <g key={i} transform={`translate(${x} ${Number(y) + 20})`} opacity={s(i * 3)}>
              <rect width={120} height={88} rx={6} fill="#c9a77c" stroke="#9b7c52" strokeWidth={3} />
              <line x1={60} x2={60} y1={0} y2={88} stroke="#9b7c52" strokeWidth={3} />
              {i % 2 === 0 ? <text x={60} y={58} fontSize={15} fill={MUNDO.vino} textAnchor="middle" style={fuente}>{lado === "A" ? "DEVUELTO" : "LISTO"}</text> : null}
            </g>
          ))}
        </g>
      );
    case "ficha":
      return (
        <g>
          <rect x={30} y={20} width={210} height={270} rx={10} fill="#f3ece0" opacity={s(0)} />
          <path d="M 80 70 L 110 60 Q 135 78 160 60 L 190 70 L 215 105 L 195 115 L 190 105 L 190 220 L 80 220 L 80 105 L 75 115 L 55 105 Z" fill="#fff" stroke="#2f2f35" strokeWidth={3} opacity={s(3)} />
          <line x1={80} x2={190} y1={240} y2={240} stroke={MUNDO.vino} strokeWidth={4} opacity={s(6)} />
          {["Medidas", "Tela", "Costuras", "Acabados"].map((t, i) => (
            <g key={t} opacity={s(6 + i * 4)}>
              <rect x={270} y={30 + i * 64} width={240} height={50} rx={10} fill="#e4ddce" />
              <text x={290} y={55 + i * 64} fontSize={22} fill={MUNDO.tinta} dominantBaseline="central" style={fuente}>{t}</text>
              <text x={488} y={56 + i * 64} fontSize={28} fill={MUNDO.vinoClaro} textAnchor="middle" dominantBaseline="central" fontWeight={900}>✓</text>
            </g>
          ))}
        </g>
      );
    case "maquina": {
      // Dos máquinas de coser. En A la aguja está parada y la prenda a medias; en B cosen la costura entera.
      const b = lado === "B";
      const puntada = Math.max(0, Math.min(1, s(6)));
      return (
        <g>
          {[0, 1].map((i) => (
            <g key={i} transform={`translate(${40 + i * 250} ${40})`} opacity={s(i * 6)}>
              <rect x={0} y={150} width={230} height={22} rx={6} fill="#6e5a46" />
              <rect x={10} y={96} width={210} height={54} rx={10} fill={b ? "#efe9dd" : "#a9a295"} />
              <rect x={18} y={16} width={56} height={86} rx={12} fill={b ? "#efe9dd" : "#a9a295"} />
              <rect x={18} y={16} width={186} height={26} rx={12} fill={b ? "#e3dccb" : "#b9b1a0"} />
              <rect x={176} y={34} width={16} height={58} rx={6} fill={b ? "#c9c2b0" : "#bdb5a8"} />
              <line x1={184} y1={92} x2={184} y2={116} stroke={b ? MUNDO.vino : "#8d857a"} strokeWidth={5} strokeLinecap="round" />
              <circle cx={46} cy={60} r={16} fill={b ? MUNDO.vino : "#bdb5a8"} opacity={0.9} />
              {/* La tela y su costura */}
              <rect x={60} y={116} width={150} height={34} rx={5} fill={b ? "#f6f1e6" : "#a9a295"} />
              {b ? (
                <line x1={70} y1={133} x2={70 + 120 * puntada} y2={133} stroke={MUNDO.vino} strokeWidth={4} strokeDasharray="9 7" />
              ) : (
                <text x={135} y={134} fontSize={34} fill="#b2283a" textAnchor="middle" dominantBaseline="central" fontWeight={900}>?</text>
              )}
            </g>
          ))}
          <text x={270} y={268} fontSize={26} fill={b ? MUNDO.vinoClaro : "#8d857a"} textAnchor="middle" dominantBaseline="central" style={fuente}>
            {b ? "MISMA COSTURA SIEMPRE" : "CADA UNA DISTINTA"}
          </text>
        </g>
      );
    }
    case "agenda":
      return (
        <g>
          {[0, 1, 2, 3].map((f) =>
            [0, 1, 2, 3].map((c) => {
              const idx = f * 4 + c;
              const llena = [1, 4, 6, 11, 13].includes(idx);
              const t = s(idx * 1.5);
              return <rect key={idx} x={30 + c * 122} y={24 + f * 70} width={110} height={58} rx={10} fill={llena ? MUNDO.vino : "#e4ddce"} opacity={llena ? t : 1} />;
            }),
          )}
        </g>
      );
    case "catalogo":
      return (
        <g>
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <g key={i} transform={`translate(${40 + (i % 3) * 160} ${24 + Math.floor(i / 3) * 140}) scale(${s(i * 3)})`}>
              <rect width={140} height={124} rx={12} fill="#f3ece0" />
              <rect x={45} y={26} width={50} height={70} rx={8} fill={[MUNDO.vino, "#d9a441", "#6c5a7d", "#3f5163", "#5f7a5c", "#c58c63"][i]} />
            </g>
          ))}
        </g>
      );
    case "render":
    default: {
      const b = lado === "B";
      return (
        <g>
          <rect x={30} y={20} width={480} height={270} rx={12} fill={b ? "#efe5d2" : "#cfc7b6"} />
          <rect x={30} y={200} width={480} height={90} fill={b ? MUNDO.madera : "#b9b1a0"} opacity={s(2)} />
          {b ? (
            <g opacity={s(6)}>
              <rect x={90} y={150} width={220} height={70} rx={12} fill="#6f7f8f" />
              <rect x={120} y={50} width={90} height={70} fill="#fff" stroke="#3d3a35" strokeWidth={5} />
              <rect x={380} y={110} width={40} height={110} rx={20} fill="#6f8a5e" />
            </g>
          ) : (
            <g opacity={s(4)}>
              {[0, 1, 2, 3].map((i) => (
                <rect key={i} x={70 + i * 40} y={60 + (i % 2) * 20} width={36} height={18} fill="#9b5a44" />
              ))}
              <text x={360} y={120} fontSize={90} fill="#b2283a" textAnchor="middle" dominantBaseline="central" fontWeight={900}>?</text>
            </g>
          )}
        </g>
      );
    }
  }
};

// ------------------------------------------------------------------ mitades

const Anillo: React.FC<{ valor: number; lado: Lado; estado: string; k: number }> = ({ valor, lado, estado, k }) => {
  const r = 92;
  const c = 2 * Math.PI * r;
  const color = lado === "A" ? "#b2283a" : MUNDO.vinoClaro;
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14, fontFamily: FUENTE }}>
      <svg width={220} height={220} viewBox="0 0 220 220">
        <circle cx={110} cy={110} r={r} stroke="#dcd4c4" strokeWidth={18} fill="none" />
        <circle
          cx={110}
          cy={110}
          r={r}
          stroke={color}
          strokeWidth={18}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={`${(c * valor).toFixed(1)} ${c.toFixed(1)}`}
          transform="rotate(-90 110 110)"
        />
        <text x={110} y={114} fontSize={86} fontWeight={900} fill={color} textAnchor="middle" dominantBaseline="central" fontFamily={FUENTE}>
          {lado === "A" ? "✕" : "✓"}
        </text>
      </svg>
      <div key={estado} style={{ fontSize: 24, fontWeight: 900, letterSpacing: "0.12em", color, opacity: interpolate(k, [0, 8], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }}>
        {estado}
      </div>
    </div>
  );
};

const Mitad: React.FC<{
  lado: Lado; nombre: string; plano: PlanoDuelo | null; activa: boolean; k: number; valor: number; sello: string | null; kSello: number;
  /** Escalonado de entrada del panel (>1 en el gancho) y lado con el que se dibuja su contenido. */
  paso?: number; ladoContenido?: Lado;
}> = ({ lado, nombre, plano, activa, k, valor, sello, kSello, paso = 1, ladoContenido }) => {
  // Sobre fondo crema un 0.42 borraba la mitad inactiva y el reel se veía medio muerto.
  // 0.74 la deja legible como "el otro lado sigue ahí", sin robarle el foco al activo.
  const brillo = activa ? 1 : 0.74;
  const entra = plano ? spring({ frame: Math.max(0, k), fps: 30, config: { damping: 16, stiffness: 170 } }) : 1;
  const selloK = sello ? spring({ frame: Math.max(0, kSello), fps: 30, config: { damping: 11, stiffness: 240, mass: 0.7 } }) : 0;
  return (
    <div style={{ position: "relative", width: 900, height: 420, opacity: brillo, transform: `scale(${activa ? 1 : 0.985})`, fontFamily: FUENTE }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
        <span style={{ fontSize: 22, fontWeight: 900, letterSpacing: "0.14em", color: "#fff", padding: "6px 16px", borderRadius: 999, backgroundColor: lado === "A" ? "#6f675c" : MUNDO.vino }}>
          {`${nombre.toUpperCase()} ${lado}`}
        </span>
        <span style={{ fontSize: 22, fontWeight: 700, color: "#6f675c" }}>{lado === "A" ? "sin sistema" : "con El Socio"}</span>
      </div>
      <div style={{ display: "flex", gap: 30, alignItems: "center" }}>
        <div
          style={{
            width: 560,
            height: 340,
            borderRadius: 22,
            backgroundColor: "#f3ece0",
            border: `2px solid ${activa ? (lado === "A" ? "#d8b3b6" : MUNDO.vino) : "#dcd4c4"}`,
            boxShadow: activa && lado === "B" ? "0 0 60px rgba(178,35,55,0.35)" : "0 16px 30px rgba(0,0,0,0.13)",
            overflow: "hidden",
          }}
        >
          <div style={{ height: 34, display: "flex", gap: 8, alignItems: "center", padding: "0 16px", backgroundColor: "#ddd5c5" }}>
            {["#b2283a", "#d9a441", "#7d9a78"].map((c) => (
              <span key={c} style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: c }} />
            ))}
          </div>
          <svg width={556} height={300} viewBox="0 0 540 300" style={{ transform: `translateY(${((1 - entra) * 40).toFixed(1)}px)`, opacity: Math.min(1, entra * 1.5) }}>
            {plano ? (
              <ContenidoPanel panel={plano.panel} k={k} lado={ladoContenido ?? lado} paso={paso} />
            ) : (
              <g>
                {[0, 1, 2].map((i) => (
                  <circle key={i} cx={240 + i * 30} cy={150} r={9} fill="#b4aca0" />
                ))}
              </g>
            )}
          </svg>
        </div>
        <Anillo valor={valor} lado={lado} estado={plano ? plano.estado : lado === "B" ? "ESPERANDO" : "..."} k={k} />
      </div>
      {sello ? (
        <div
          style={{
            position: "absolute",
            left: 170,
            top: 140,
            transform: `rotate(-10deg) scale(${(2.2 - 1.2 * selloK).toFixed(3)})`,
            opacity: Math.min(1, selloK * 1.6),
            fontSize: 110,
            fontWeight: 900,
            color: lado === "A" ? "#b2283a" : "#fff",
            border: `10px solid ${lado === "A" ? "#b2283a" : "#fff"}`,
            backgroundColor: lado === "A" ? "rgba(255,255,255,0.82)" : MUNDO.vino,
            padding: "0 36px",
            borderRadius: 16,
            letterSpacing: "0.04em",
          }}
        >
          {sello}
        </div>
      ) : null}
    </div>
  );
};

// ------------------------------------------------------------------ componente

export const ReelDuelo: React.FC<PropsReel> = (props) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const seg = frame / fps;
  const { planos, nombre } = resolverDuelo(props, durationInFrames / fps);
  const i = segmentoEn(planos, seg);
  const p = planos[i];
  const k = frame - Math.round(p.inicio * fps);

  // Cada mitad muestra el último plano de su lado que ya sonó (se queda con su estado).
  const ultimo = (l: Lado) => {
    for (let j = i; j >= 0; j--) if (planos[j].lado === l && planos[j].tipo === "bloque") return planos[j];
    return null;
  };
  // En el gancho las dos mitades enseñan el MISMO encargo (la mecánica de "Mismo tema. Mismas ganas."
  // de la referencia). Antes esperaban vacías con "..." y el reel abría con 3.5 s de pantalla muerta.
  const enGancho = p.tipo === "gancho";
  const primerBloque = planos.find((x) => x.tipo === "bloque") ?? null;
  const planoGancho: PlanoDuelo | null = primerBloque ? { ...primerBloque, estado: "MISMO ENCARGO", inicio: 0 } : null;
  const pa = enGancho ? planoGancho : ultimo("A");
  const pb = enGancho ? planoGancho : ultimo("B");
  const nA = planos.slice(0, i + 1).filter((x) => x.lado === "A" && x.tipo === "bloque").length;
  const nB = planos.slice(0, i + 1).filter((x) => x.lado === "B" && x.tipo === "bloque").length;
  const suave = (objetivo: number, desde: number) =>
    interpolate(k, [0, 14], [desde, objetivo], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  const valorA = p.lado === "A" && p.tipo === "bloque" ? suave(Math.max(0.08, 1 - nA * 0.28), Math.max(0.08, 1 - (nA - 1) * 0.28)) : Math.max(0.08, 1 - nA * 0.28);
  const valorB = p.lado === "B" && p.tipo === "bloque" ? suave(Math.min(1, 0.15 + nB * 0.28), Math.min(1, 0.15 + (nB - 1) * 0.28)) : nB ? Math.min(1, 0.15 + nB * 0.28) : 0.04;
  // En el gancho los dos medidores arrancan iguales: todavía no pasó nada que los separe.
  const medidorGancho = interpolate(frame, [0, 26], [0, 0.62], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });

  const kA = pa ? frame - Math.round(pa.inicio * fps) : 0;
  // En el gancho el lado B recibe el encargo un poco después que A: así el ojo ve llegar los dos.
  const kB = enGancho ? frame - 12 : pb ? frame - Math.round(pb.inicio * fps) : 0;
  const pasoGancho = 5;
  const esCierreA = p.tipo === "cierre" && !p.final && p.lado === "A";
  const esCierreB = p.tipo === "cierre" && !p.final && p.lado === "B";
  const activaA = p.tipo === "gancho" || p.lado === "A";
  const activaB = p.tipo === "gancho" || p.lado === "B";

  const moneda = spring({ frame, fps, config: { damping: 10, stiffness: 120 } });
  const pulso = 1 + Math.sin(frame * 0.2) * 0.03;

  return (
    <AbsoluteFill style={{ background: "linear-gradient(to bottom, #f7f3ea 0%, #f1ece0 54%, #efe7db 100%)", overflow: "hidden", fontFamily: FUENTE }}>
      <div style={{ position: "absolute", left: 0, right: 0, top: 1060, height: 700, background: "radial-gradient(ellipse at 50% 0%, rgba(156,28,46,0.10), transparent 60%)" }} />

      <div style={{ position: "absolute", top: SAFE_TOP + 10, left: 70, width: 1080 - 70 - 120 }}>
        {p.final ? null : (
          <Titular
            key={p.indice}
            texto={p.texto}
            inicioFrame={Math.round(p.inicio * fps)}
            finFrame={Math.round(p.fin * fps)}
            frame={frame}
            fps={fps}
            inmediato={p.tipo === "gancho"}
            colorTexto={MUNDO.tinta}
            colorFantasma="#a49d90"
            escala={0.86}
          />
        )}
      </div>

      <div style={{ position: "absolute", left: 76, top: 610 }}>
        <Mitad lado="A" nombre={nombre} plano={pa} activa={activaA} k={kA} valor={enGancho ? medidorGancho : valorA} sello={esCierreA ? "NO" : null} kSello={k - 4} paso={enGancho ? pasoGancho : 1} ladoContenido={enGancho ? "A" : undefined} />
      </div>

      {/* Línea y moneda VS */}
      <div style={{ position: "absolute", left: 0, right: 0, top: 1062, height: 4, background: `linear-gradient(to right, transparent, ${MUNDO.vinoClaro} 20%, #f3d9a4 50%, ${MUNDO.vinoClaro} 80%, transparent)`, boxShadow: "0 0 24px rgba(178,35,55,0.8)" }} />
      <div
        style={{
          position: "absolute",
          left: 540 - 62,
          top: 1064 - 62,
          width: 124,
          height: 124,
          borderRadius: 62,
          background: `radial-gradient(circle at 35% 30%, #c83a4e, ${MUNDO.vino} 60%, ${MUNDO.vinoOscuro})`,
          border: "5px solid #f3d9a4",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#f5f0e6",
          fontSize: 50,
          fontWeight: 900,
          fontStyle: "italic",
          transform: `scale(${(moneda * pulso).toFixed(3)}) rotate(${((1 - moneda) * 360).toFixed(1)}deg)`,
          boxShadow: "0 0 40px rgba(178,35,55,0.6)",
        }}
      >
        VS
      </div>

      <div style={{ position: "absolute", left: 76, top: 1125 }}>
        <Mitad lado="B" nombre={nombre} plano={pb} activa={activaB} k={kB} valor={enGancho ? medidorGancho : valorB} sello={esCierreB ? "SÍ" : null} kSello={k - 4} paso={enGancho ? pasoGancho : 1} ladoContenido={enGancho ? "A" : undefined} />
      </div>

      {p.final ? <TarjetaMarca frameLocal={k} fps={fps} texto={p.texto} /> : null}
    </AbsoluteFill>
  );
};
