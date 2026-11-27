import React from "react";
import { z } from "zod";
import { AbsoluteFill, Easing, interpolate, spring } from "remotion";
import { MUNDO } from "./mundo/base";
import type { NombreNicho } from "./mundo/interiores";

/**
 * Piezas que comparten TODOS los formatos de Reel de El Socio (Mundo, Collage, Duelo):
 * línea de tiempo sincronizada con la voz, deducción de nicho y lado, titular palabra por palabra,
 * cierre de venta en golpes y tarjeta de marca final. Un formato nuevo solo decide QUÉ se ve.
 */

export const FORMATOS = ["mundo", "collage", "duelo"] as const;
export type Formato = (typeof FORMATOS)[number];

export const GANCHO_SEG = 2.4;
export const CADENCIA_SEG = 2.6;
export const CIERRE_SEG = 3.2;
export const FINAL_SEG = 2.2; // tarjeta de marca final: mínimo en pantalla
export const FPS = 30;
export const SAFE_TOP = 220;
export const SAFE_BOTTOM = 380;
export const FUENTE = "-apple-system,BlinkMacSystemFont,'SF Pro Display','SF Pro Text','Segoe UI',Helvetica,Arial,sans-serif";

export const TIPOS_TARJETA_REEL = ["correo", "agenda", "ficha", "catalogo", "render", "chat", "ninguna"] as const;

export const planoSchema = z.object({
  toma: z.enum(["ciudad", "pareja", "calle", "local", "detalle"]).optional(),
  lado: z.enum(["A", "B"]).optional(),
  foco: z.string().optional(),
  objeto: z.string().optional(),
  estado: z.enum(["caos", "orden"]).optional(),
  tooltip: z.string().optional(),
  tarjeta: z.enum(TIPOS_TARJETA_REEL).optional(),
});
export type PlanoEntrada = z.infer<typeof planoSchema>;

export const reelSchema = z.object({
  gancho: z.string(),
  bloques: z.array(z.string()),
  cierre: z.string(),
  nicho: z.string().optional(),
  badge: z.string().optional(),
  etiquetas: z.array(z.string()).optional(),
  planos: z.array(planoSchema).optional(),
  formato: z.string().optional(),
  tiemposBloques: z.array(z.number()).optional(),
  tiempoCierre: z.number().optional(),
  tiemposCortes: z.array(z.number()).optional(),
  duracionFrames: z.number().optional(),
  escena: z.string().optional(),
  /** Hora del día de la escena: dia | atardecer | noche | nublado (ver AMBIENTES en ReelMundo). */
  ambiente: z.string().optional(),
  /** Número del reparto: cambia la gente del escenario entre REELES, nunca dentro de uno. */
  reparto: z.number().optional(),
});
export type PropsReel = z.infer<typeof reelSchema>;

export const NOMBRE_LOTE: Record<NombreNicho, string> = { taller: "Taller", obra: "Local", estudio: "Tienda", oficina: "Agencia" };
export const BADGE_NICHO: Record<NombreNicho, string> = { taller: "CONFECCIÓN", obra: "ESPACIOS", estudio: "CATÁLOGO", oficina: "AGENCIAS" };

// ------------------------------------------------------------------ vocabulario

export const normalizar = (s: string) =>
  (s || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");

export const NICHO_POR_ID: Record<string, NombreNicho> = {
  "fichas-tecnicas-ropa": "taller",
  "modelado-3d-espacios": "obra",
  "ecommerce-catalogo-visual": "estudio",
  "automatizacion-agencias-estudios": "oficina",
  taller: "taller",
  obra: "obra",
  estudio: "estudio",
  oficina: "oficina",
};

export const PALABRAS_NICHO: Record<NombreNicho, RegExp> = {
  taller: /taller|confecc|costur|patron|tela|prenda|ropa|coleccion|lote|muestra|marca de ropa|corte/,
  obra: /remodel|obra|pared|sala|habitaci|espacio|local|render|plano|apartament|casa|mueble|cocina|arquitect|maestro/,
  estudio: /catalogo|foto|producto|tienda|inventario|ecommerce|e-commerce|instagram|vitrina|modelo/,
  oficina: /correo|email|cliente|agenda|reunion|seguimiento|lead|agencia|bandeja|mensaje|whatsapp|llamada|propuesta|cita/,
};


// El lado B es el negocio que ya tiene sistema. "tu socio"/"su socio" estaban fuera de la lista
// y el cerebro escribe justamente "Con tu Socio": por eso frases de solución caían en el lado del
// caos, con pared fría y rótulo negativo ("Con tu Socio, ves el espacio terminado" → TODO A MANO).
export const PALABRAS_LADO_B = /\b(el otro|la otra|otro|otra recibe|nosotros|el socio|tu socio|su socio|al otro|en el otro|ese taller|esa tienda|ese local|esa agencia|ese estudio|con un|con una|sistema|herramienta|ahora|resuelto|queda listo|listo|exact|sin adivinar|sin sorpresas|sin mover|resultado|ya habias visto|primero|luego|despues)\b/;
export const PALABRAS_LADO_A = /\b(uno|una recibe|sin sistema|adivina|interpreta|a su manera|a ciegas|a mano|otra vez|rehacer|tumbar|reproceso|nadie|perdiste|tarde|nunca|hoy|espera|no vuelven)\b/;

export const ARTICULO: Record<NombreNicho, string> = { taller: "el", obra: "el", estudio: "la", oficina: "la" };
export const LINEA_MARCA = "Con El Socio, te lo solucionamos.";

/**
 * El cierre es de VENTA, no una despedida: "No seas el Taller A. Sé el Taller B. Con El Socio,
 * te lo solucionamos." Cada oración es un golpe con su propia toma; la última es la tarjeta de marca.
 * "Link en bio" no va nunca dentro del video (se ve barato): eso vive en el pie de publicación.
 */
export const frasesCierre = (cierre: string, nicho: NombreNicho): string[] => {
  const limpio = (cierre || "")
    .replace(/\s*[·|\-–—]?\s*(el\s+)?link en (la\s+)?bio\.?/gi, "")
    .trim();
  const partes = (limpio.match(/[^.!?]+[.!?]?/g) || []).map((t) => t.trim()).filter(Boolean);
  if (partes.length >= 2 && /socio/i.test(partes[partes.length - 1])) return partes;
  const n = NOMBRE_LOTE[nicho];
  const a = ARTICULO[nicho];
  return [`No seas ${a} ${n} A.`, `Sé ${a} ${n} B.`, LINEA_MARCA];
};

export const deducirNicho = (nicho: string | undefined, textos: string[]): NombreNicho => {
  const clave = (nicho || "").trim().toLowerCase();
  if (NICHO_POR_ID[clave]) return NICHO_POR_ID[clave];
  const todo = normalizar(textos.join(" "));
  let mejor: NombreNicho = "taller";
  let puntos = -1;
  (Object.keys(PALABRAS_NICHO) as NombreNicho[]).forEach((n) => {
    const m = todo.match(new RegExp(PALABRAS_NICHO[n].source, "g"));
    const p = m ? m.length : 0;
    if (p > puntos) {
      puntos = p;
      mejor = n;
    }
  });
  return mejor;
};

export type Lado = "A" | "B";
export type TipoSegmento = "gancho" | "bloque" | "cierre";

export type Segmento = {
  indice: number;
  tipo: TipoSegmento;
  texto: string;
  inicio: number;
  fin: number;
  /** Último golpe del cierre: tarjeta de marca a pantalla completa. */
  final: boolean;
};

/** Lado A (sin sistema) o B (con El Socio) de una frase, por palabras y por posición. */
export const ladoDe = (seg: Segmento, nBloques: number, explicito?: Lado): Lado => {
  if (explicito) return explicito;
  const t = normalizar(seg.texto);
  if (seg.tipo === "gancho") return "A";
  if (seg.tipo === "cierre") return /\bA\b/.test(seg.texto) && !/\bB\b/.test(seg.texto) ? "A" : "B";
  // Antes se exigía exclusividad: una frase con palabras de los dos lados ("Con tu Socio ... antes
  // de romper una pared") no contaba para ninguno y caía al reparto por posición. Ahora gana el
  // lado que más señales tenga, y la posición solo decide los empates de verdad.
  const cuenta = (re: RegExp) => (t.match(new RegExp(re.source, "g")) || []).length;
  const nB = cuenta(PALABRAS_LADO_B);
  const nA = cuenta(PALABRAS_LADO_A);
  if (nB !== nA) return nB > nA ? "B" : "A";
  return seg.indice - 1 < Math.max(1, Math.floor(nBloques / 2)) ? "A" : "B";
};

export const duracionReel = (p: { bloques?: string[]; duracionFrames?: number; cierre?: string; gancho?: string; nicho?: string }): number => {
  if (p.duracionFrames && p.duracionFrames > 0) return p.duracionFrames;
  const nicho = deducirNicho(p.nicho, [p.gancho || "", ...(p.bloques || [])]);
  const nFrases = frasesCierre(p.cierre || "", nicho).length;
  const cierreSeg = Math.max(CIERRE_SEG, (nFrases - 1) * 1.6 + FINAL_SEG);
  return Math.round((GANCHO_SEG + (p.bloques?.length ?? 6) * CADENCIA_SEG + cierreSeg) * FPS);
};

/**
 * Línea de tiempo del reel: gancho, bloques y golpes del cierre, cada uno con su inicio y fin en segundos.
 * Si la voz ya se generó (`tiemposBloques`, `tiempoCierre`), los cortes caen exactamente donde empieza
 * cada frase hablada. Los golpes del cierre se reparten el tramo final según su largo.
 */
export const segmentosReel = (props: PropsReel, duracionSeg: number): { nicho: NombreNicho; segmentos: Segmento[] } => {
  const { gancho, bloques = [], cierre, tiemposBloques, tiempoCierre } = props;
  const nicho = deducirNicho(props.nicho, [gancho, ...bloques, cierre]);
  const golpes = frasesCierre(cierre, nicho);
  const textos: { tipo: TipoSegmento; texto: string }[] = [
    { tipo: "gancho", texto: gancho },
    ...bloques.map((b) => ({ tipo: "bloque" as const, texto: b })),
    ...golpes.map((g) => ({ tipo: "cierre" as const, texto: g })),
  ];
  const nCuerpo = 1 + bloques.length;
  const sinc = Array.isArray(tiemposBloques) && tiemposBloques.length === bloques.length;
  const tFinGancho = sinc ? Math.max(1.2, tiemposBloques![0]) : GANCHO_SEG;
  const tCierre = typeof tiempoCierre === "number" && tiempoCierre > tFinGancho ? tiempoCierre : GANCHO_SEG + bloques.length * CADENCIA_SEG;
  const tramoCierre = Math.max(1.5, duracionSeg - tCierre);
  const pesos = golpes.map((g) => Math.max(8, g.length));
  const totalPesos = pesos.reduce((a, b) => a + b, 0);
  const iniciosCierre: number[] = [];
  let acum = tCierre;
  golpes.forEach((_, k) => {
    iniciosCierre.push(acum);
    acum += (tramoCierre * pesos[k]) / totalPesos;
  });
  const ultimo = iniciosCierre.length - 1;
  if (ultimo > 0 && duracionSeg - iniciosCierre[ultimo] < FINAL_SEG) {
    const corrida = Math.min(iniciosCierre[ultimo] - iniciosCierre[ultimo - 1] - 0.8, FINAL_SEG - (duracionSeg - iniciosCierre[ultimo]));
    if (corrida > 0) for (let k = 1; k <= ultimo; k++) iniciosCierre[k] -= (corrida * k) / ultimo;
  }
  const inicios = textos.map((_, i) => {
    if (i === 0) return 0;
    if (i >= nCuerpo) return iniciosCierre[i - nCuerpo];
    return sinc ? tiemposBloques![i - 1] : tFinGancho + (i - 1) * CADENCIA_SEG;
  });
  const segmentos = textos.map((t, i) => ({
    indice: i,
    tipo: t.tipo,
    texto: t.texto,
    inicio: inicios[i],
    fin: i + 1 < textos.length ? inicios[i + 1] : duracionSeg,
    final: t.tipo === "cierre" && i === textos.length - 1,
  }));
  return { nicho, segmentos };
};

/** Segmento activo en un instante. */
export const segmentoEn = (segmentos: Segmento[], seg: number): number => {
  let i = 0;
  for (let k = 0; k < segmentos.length; k++) if (seg >= segmentos[k].inicio) i = k;
  return i;
};

// ------------------------------------------------------------------ texto

// ------------------------------------------------------------------ texto

export const STOP = new Set(
  "el la los las un una unos unas de del al a en con sin por para que como cuando donde tu tus su sus mi mis te se lo le les me nos ya no si es son fue era esta estan ser hay va van muy mas pero o y e ni otro otra este esta esto ese esa eso link bio asi todo cada uno dos".split(" "),
);
export const FUERTES = new Set(
  "ciegas reprocesos problema resuelto sistema agenda agendado taller plano render clientes cliente ventas tiempo nunca siempre solo sorpresas medidas ficha catalogo entrega listo pared remodelacion lote adivina adivino lleno foto correo arruinar arruina pierdes perder caro reprocesos devuelto".split(" "),
);

export const palabraClave = (palabras: string[]): number => {
  let mejor = -1;
  let pts = -1;
  // En los golpes del cierre ("Sé el Taller B.") lo que importa es la letra: A o B.
  const ultima = palabras.length - 1;
  if (ultima >= 0 && /(^|\u00a0)[AB][.!]?$/.test(palabras[ultima])) return ultima;
  palabras.forEach((p, i) => {
    const l = normalizar(p).replace(/[^a-z]/g, "");
    if (!l || STOP.has(l)) return;
    let s = l.length + (FUERTES.has(l) ? 20 : 0) + (i >= palabras.length / 2 ? 3 : 0);
    if (s > pts) {
      pts = s;
      mejor = i;
    }
  });
  return mejor >= 0 ? mejor : palabras.length - 1;
};

/**
 * Reparte las palabras de una frase en el tiempo que dura su voz. El peso de cada palabra es su
 * largo (decir "remodelación" tarda más que decir "el"), así el resalte cae donde está la voz sin
 * necesitar transcripción. Devuelve el frame en que empieza cada palabra.
 */
export const tiemposPalabras = (palabras: string[], inicioFrame: number, finFrame: number): number[] => {
  const dur = Math.max(6, finFrame - inicioFrame);
  const pesos = palabras.map((p) => Math.max(2, p.replace(/[^\p{L}\p{N}]/gu, "").length) + 1.6);
  const total = pesos.reduce((a, b) => a + b, 0);
  const inicios: number[] = [];
  let acum = 0;
  pesos.forEach((w) => {
    inicios.push(inicioFrame + (acum / total) * dur);
    acum += w;
  });
  return inicios;
};

export const Titular: React.FC<{
  texto: string; inicioFrame: number; finFrame?: number; frame: number; fps: number; inmediato?: boolean;
  colorTexto?: string; colorFantasma?: string; escala?: number;
}> = ({ texto, inicioFrame, finFrame, frame, fps, inmediato = false, colorTexto = MUNDO.tinta, colorFantasma = "#a49d90", escala = 1 }) => {
  const palabras = texto.trim().split(/\s+/).filter(Boolean);
  // "Agencia A." va pegado: la letra nunca queda sola en otra línea.
  if (palabras.length > 1 && /^[AB][.!]?$/.test(palabras[palabras.length - 1])) {
    const letra = palabras.pop() as string;
    palabras[palabras.length - 1] += `\u00a0${letra}`;
  }
  const ventana = Math.min(11, Math.max(4, palabras.length * 1.6));
  const largo = texto.length;
  const fontSize = (largo <= 22 ? 92 : largo <= 40 ? 80 : largo <= 60 ? 68 : 58) * escala;
  // El resalte sigue la voz: viaja palabra por palabra durante toda la frase, no se queda clavado.
  const fin = typeof finFrame === "number" && finFrame > inicioFrame + 6 ? finFrame : inicioFrame + palabras.length * 9;
  const voz = tiemposPalabras(palabras, inicioFrame, fin - Math.min(12, (fin - inicioFrame) * 0.12));
  let hablando = -1;
  for (let k = 0; k < voz.length; k++) if (frame >= voz[k]) hablando = k;
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        justifyContent: "center",
        columnGap: fontSize * 0.08,
        rowGap: fontSize * 0.08,
        fontSize,
        fontWeight: 900,
        letterSpacing: "-0.035em",
        lineHeight: 1.08,
        textAlign: "center",
      }}
    >
      {palabras.map((p, i) => {
        const f0 = inmediato ? inicioFrame - 8 : inicioFrame + (palabras.length <= 1 ? 0 : (i / (palabras.length - 1)) * ventana);
        const a = interpolate(frame, [f0, f0 + 7], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
        const asentada = frame >= f0 + 4;
        const esClave = i === hablando && asentada;
        const golpe = esClave ? spring({ frame: Math.max(0, frame - voz[i]), fps, config: { damping: 12, stiffness: 220, mass: 0.5 } }) : 1;
        return (
          <span
            key={i}
            style={{
              // El relleno es el mismo en toda palabra y solo cambia el color del fondo: así el
              // cuadro rojo salta de palabra en palabra sin que el texto se reacomode.
              display: "inline-block",
              opacity: a <= 0.01 ? 0 : Math.min(1, a * 1.3),
              transform: `translateY(${((1 - a) * 18).toFixed(1)}px) scale(${esClave ? (0.93 + golpe * 0.07).toFixed(3) : 1})`,
              color: esClave ? MUNDO.blanco : asentada ? colorTexto : colorFantasma,
              backgroundColor: esClave ? MUNDO.vino : "transparent",
              padding: `0 ${fontSize * 0.1}px ${fontSize * 0.04}px`,
              borderRadius: fontSize * 0.14,
            }}
          >
            {p}
          </span>
        );
      })}
    </div>
  );
};

// ------------------------------------------------------------------ tarjeta de marca final

// ------------------------------------------------------------------ tarjeta de marca final

/**
 * Cierre elegante: la escena se cubre de crema desde abajo, aparece la marca (sombrero + gafas +
 * "El Socio") y la línea de venta. Sin "link en bio", sin flechas, sin botones de Facebook viejo.
 */
export const TarjetaMarca: React.FC<{ frameLocal: number; fps: number; texto: string }> = ({ frameLocal, fps, texto }) => {
  const cubre = interpolate(frameLocal, [0, 11], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic) });
  const logo = spring({ frame: Math.max(0, frameLocal - 8), fps, config: { damping: 13, mass: 0.7, stiffness: 160 } });
  const linea = spring({ frame: Math.max(0, frameLocal - 16), fps, config: { damping: 16, stiffness: 170 } });
  const subraya = interpolate(frameLocal, [24, 36], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  const limpio = (texto || LINEA_MARCA).trim();
  const coma = limpio.indexOf(",");
  const arriba = coma > 0 ? limpio.slice(0, coma + 1) : "";
  const abajo = coma > 0 ? limpio.slice(coma + 1).trim() : limpio;
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          height: `${(cubre * 100).toFixed(2)}%`,
          backgroundColor: MUNDO.crema,
          backgroundImage: "linear-gradient(to right, rgba(10,10,10,0.04) 1px, transparent 1px), linear-gradient(to bottom, rgba(10,10,10,0.04) 1px, transparent 1px)",
          backgroundSize: "54px 54px",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 76,
          right: 160,
          top: SAFE_TOP,
          bottom: SAFE_BOTTOM,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 34,
          fontFamily: FUENTE,
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14, opacity: Math.min(1, logo * 1.4), transform: `scale(${(0.8 + 0.2 * logo).toFixed(3)})` }}>
          <svg width={190} height={146} viewBox="0 0 68 52" fill="none">
            <rect x={20} y={4} width={28} height={20} rx={2} fill={MUNDO.tinta} />
            <rect x={20} y={19} width={28} height={4} fill={MUNDO.vino} />
            <ellipse cx={34} cy={25} rx={24} ry={3.5} fill={MUNDO.tinta} />
            <circle cx={24} cy={38} r={6.5} stroke={MUNDO.tinta} strokeWidth={2.6} />
            <circle cx={44} cy={38} r={6.5} stroke={MUNDO.tinta} strokeWidth={2.6} />
            <path d="M 30.5 38 Q 34 34.5 37.5 38" stroke={MUNDO.tinta} strokeWidth={2.4} />
          </svg>
          <div style={{ fontFamily: "'Playfair Display', Georgia, serif", fontWeight: 800, fontSize: 100, letterSpacing: "-0.02em", color: MUNDO.tinta }}>El Socio</div>
        </div>
        <div style={{ width: 120 * subraya, height: 3, backgroundColor: MUNDO.vino }} />
        <div
          style={{
            textAlign: "center",
            opacity: Math.min(1, linea * 1.4),
            transform: `translateY(${((1 - linea) * 26).toFixed(1)}px)`,
            color: MUNDO.tinta,
            fontWeight: 900,
            letterSpacing: "-0.03em",
            lineHeight: 1.12,
          }}
        >
          {arriba ? <div style={{ fontSize: 62, fontWeight: 700, color: "#4a453d", marginBottom: 6 }}>{arriba}</div> : null}
          <div style={{ fontSize: 74 }}>
            <span style={{ backgroundColor: MUNDO.vino, color: "#fff", padding: "0 18px 6px", borderRadius: 12 }}>{abajo}</span>
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
