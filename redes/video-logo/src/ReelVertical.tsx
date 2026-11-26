import React from "react";
import { z } from "zod";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  EscenaIsometrica,
  NOMBRES_ESCENA,
  PALETA,
  type NombreEscena,
  type TemaVisual,
} from "./EscenasIsometricas";

/**
 * Plantilla vertical 1080x1920 @ 30fps para Reels de El Socio (v2 — Alto Ritmo).
 *
 * Aplica al pie de la letra `contexto/guia-estilo-video.md`:
 *  1. Cortes visuales reales cada ~2 s (ningún plano estático dura más de 3 s / 90 frames):
 *     alterna fondo oscuro (`#0a0a0a` con grilla sutil) y fondo crema (`#f5f0e6` con grilla)
 *     en cada cambio de bloque, y añade punch-in automático a mitad de plano si una frase
 *     hablada supera ~2.5 s.
 *  2. Tipografía grotesca pesada con entrada palabra por palabra en ráfagas rápidas
 *     (9–18 frames por frase), estado fantasma -> sólido, y UNA palabra clave resaltada
 *     por frase con caja vino (`#9c1c2e`).
 *  3. Badge persistente arriba-izquierda (`● CASO REAL` / nicho sin cifras) y marca discreta
 *     de El Socio arriba-derecha, respetando zonas seguras (`SAFE_TOP`, `SAFE_BOTTOM`, `SAFE_RIGHT`).
 *  4. Texto arriba, escena isométrica animada por fase abajo, y micro-subtítulo/cierre quemado al pie.
 */

export const reelVerticalSchema = z.object({
  gancho: z.string(),
  bloques: z.array(z.string()),
  cierre: z.string(),
  nicho: z.string().optional(),
  badge: z.string().optional(),
  escena: z.enum(NOMBRES_ESCENA).optional(),
  etiquetas: z.array(z.string()).optional(),
  tiemposBloques: z.array(z.number()).optional(),
  tiempoCierre: z.number().optional(),
  tiemposCortes: z.array(z.number()).optional(),
  duracionFrames: z.number().optional(),
});

type Props = z.infer<typeof reelVerticalSchema>;

// Zonas seguras estrictas de Instagram Reels sobre 1080x1920 (`guia-estilo-video.md` §5).
const SAFE_TOP = 220;
const SAFE_BOTTOM = 380;
const SAFE_LEFT = 76;
const SAFE_RIGHT = 160;

const ANCHO_UTIL = 1080 - SAFE_LEFT - SAFE_RIGHT; // 844 px libres de botones laterales

const FUENTE =
  "-apple-system,BlinkMacSystemFont,'SF Pro Display','SF Pro Text','Segoe UI',Helvetica,Arial,sans-serif";

// Duraciones por defecto para apuntar al rango objetivo de 18–28 s con 5–7 bloques.
export const GANCHO_SEG = 2.4;
export const CADENCIA_SEG = 2.6;
export const CIERRE_SEG = 3.2;
const MAX_PLANO_ESTATICO_SEG = 2.55; // Garantiza < 3.0 s (90 frames) siempre

export const duracionEnFrames = (nBloques: number, fps = 30): number =>
  Math.round((GANCHO_SEG + Math.max(0, nBloques) * CADENCIA_SEG + CIERRE_SEG) * fps);

// ------------------------------------------------------------------ utilidades de texto sin cifras

const STOPWORDS_ES = new Set([
  "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al", "a",
  "en", "con", "sin", "por", "para", "que", "qué", "como", "cómo", "cuando", "donde",
  "tu", "tus", "su", "sus", "mi", "mis", "te", "se", "lo", "le", "les", "me", "nos",
  "ya", "no", "si", "sí", "es", "son", "fue", "era", "está", "estan", "están", "ser",
  "estar", "hay", "va", "van", "vas", "has", "han", "muy", "mas", "más", "pero", "o",
  "y", "e", "ni", "otro", "otra", "este", "esta", "esto", "ese", "esa", "eso", "link",
  "bio", "así", "asi", "todo", "toda", "todos", "todas", "cada", "uno", "dos",
]);

const PALABRAS_FUERTES = new Set([
  "ciegas", "reprocesos", "reproceso", "problema", "resuelto", "sistema", "agenda",
  "agendado", "taller", "plano", "render", "clientes", "cliente", "venta", "ventas",
  "tiempo", "caro", "tarde", "nunca", "siempre", "solo", "sorpresas", "medidas",
  "ficha", "catalogo", "catálogo", "entrega", "entregado", "listo", "calificado",
  "perdiste", "adivinó", "adivino", "culpa", "suerte", "remodelación", "remodelacion",
]);

const limpiarToken = (palabra: string): string =>
  palabra
    .toLowerCase()
    .replace(/[.,;:¡!¿?"'()[\]·—–-]/g, "")
    .trim();

/** Elige determinísticamente UNA sola palabra clave por frase para resaltar en caja vino. */
export const elegirIndicePalabraClave = (palabras: string[]): number => {
  if (palabras.length === 0) return -1;
  if (palabras.length === 1) return 0;

  let mejorIdx = -1;
  let mejorPuntaje = -1;

  palabras.forEach((bruta, idx) => {
    const limpia = limpiarToken(bruta);
    if (!limpia || STOPWORDS_ES.has(limpia)) return;
    let puntaje = limpia.length;
    if (PALABRAS_FUERTES.has(limpia)) puntaje += 20;
    // Ligera preferencia por la segunda mitad de la frase (remate retórico)
    if (idx >= Math.floor(palabras.length / 2)) puntaje += 3;
    if (puntaje > mejorPuntaje) {
      mejorPuntaje = puntaje;
      mejorIdx = idx;
    }
  });

  return mejorIdx >= 0 ? mejorIdx : palabras.length - 1;
};

const MAPA_BADGE_NICHO: Record<string, string> = {
  "modelado-3d-espacios": "ESPACIOS",
  "fichas-tecnicas-ropa": "CONFECCIÓN",
  "ecommerce-catalogo-visual": "CATÁLOGO",
  "automatizacion-agencias-estudios": "AGENCIAS",
  general: "CASO REAL",
};

const resolverBadge = (nicho?: string, badgeManual?: string): string => {
  if (badgeManual && badgeManual.trim()) {
    const limpio = badgeManual.replace(/[0-9$%]/g, "").trim().toUpperCase();
    if (limpio) return limpio.slice(0, 18);
  }
  const clave = (nicho || "").trim().toLowerCase();
  if (MAPA_BADGE_NICHO[clave]) return MAPA_BADGE_NICHO[clave];
  if (clave && clave !== "(general)") {
    const limpio = clave
      .replace(/[-_]+/g, " ")
      .replace(/[0-9$%]/g, "")
      .trim()
      .toUpperCase();
    const primera = limpio.split(/\s+/).find((w) => w.length >= 4);
    if (primera) return primera.slice(0, 16);
  }
  return "CASO REAL";
};

// ------------------------------------------------------------------ fondos con grilla editorial

const FondoConGrilla: React.FC<{ tema: TemaVisual }> = ({ tema }) => {
  const esCrema = tema === "crema";
  const colorFondo = esCrema ? PALETA.crema : PALETA.tinta;
  const imagenGrilla = esCrema
    ? `linear-gradient(to right, rgba(10,10,10,0.055) 1px, transparent 1px),
       linear-gradient(to bottom, rgba(10,10,10,0.055) 1px, transparent 1px)`
    : `radial-gradient(rgba(255,255,255,0.13) 1.6px, transparent 1.6px)`;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: colorFondo,
        backgroundImage: imagenGrilla,
        backgroundSize: esCrema ? "54px 54px" : "44px 44px",
      }}
    />
  );
};

// ------------------------------------------------------------------ cabecera persistente segura

const CabeceraPersistente: React.FC<{ badgeTexto: string; tema: TemaVisual }> = ({
  badgeTexto,
  tema,
}) => {
  const esCrema = tema === "crema";
  const colorTexto = esCrema ? PALETA.tinta : PALETA.blanco;
  const fondoBadge = esCrema ? "rgba(10,10,10,0.07)" : "rgba(255,255,255,0.08)";
  const bordeBadge = esCrema ? "rgba(10,10,10,0.16)" : "rgba(255,255,255,0.16)";

  return (
    <div
      style={{
        width: ANCHO_UTIL,
        display: "flex",
        flexDirection: "row",
        alignItems: "center",
        justifyContent: "space-between",
        marginBottom: 26,
        flex: "0 0 auto",
      }}
    >
      {/* Badge persistente arriba-izquierda (`guia-estilo-video.md` §3.4) */}
      <div
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 10,
          padding: "8px 18px",
          borderRadius: 999,
          backgroundColor: fondoBadge,
          border: `1.5px solid ${bordeBadge}`,
        }}
      >
        <span
          style={{
            width: 11,
            height: 11,
            borderRadius: "50%",
            backgroundColor: PALETA.vino,
            display: "inline-block",
          }}
        />
        <span
          style={{
            fontSize: 21,
            fontWeight: 800,
            letterSpacing: "0.1em",
            color: colorTexto,
          }}
        >
          {badgeTexto}
        </span>
      </div>

      {/* Marca discreta arriba-derecha (sombrero + gafas + nombre) */}
      <div
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 10,
          opacity: 0.78,
        }}
      >
        <svg width={34} height={26} viewBox="0 0 68 52" fill="none">
          {/* Sombrero de copa minimalista */}
          <rect x={20} y={4} width={28} height={20} rx={2} fill={colorTexto} />
          <rect x={20} y={19} width={28} height={4} fill={PALETA.vino} />
          <ellipse cx={34} cy={25} rx={24} ry={3.5} fill={colorTexto} />
          {/* Gafas icónicas */}
          <circle cx={24} cy={38} r={6.5} stroke={colorTexto} strokeWidth={2.6} />
          <circle cx={44} cy={38} r={6.5} stroke={colorTexto} strokeWidth={2.6} />
          <path d="M 30.5 38 Q 34 34.5 37.5 38" stroke={colorTexto} strokeWidth={2.4} />
        </svg>
        <span
          style={{
            fontFamily: "'Playfair Display', Georgia, serif",
            fontWeight: 800,
            fontSize: 24,
            letterSpacing: "-0.01em",
            color: colorTexto,
          }}
        >
          El Socio
        </span>
      </div>
    </div>
  );
};

// ------------------------------------------------------------------ frase palabra por palabra (9-18 frames)

const FraseEnRafaga: React.FC<{
  texto: string;
  inicioSeg: number;
  tema: TemaVisual;
  esGancho?: boolean;
  tamanoFuente?: number;
}> = ({ texto, inicioSeg, tema, esGancho = false, tamanoFuente }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const palabras = (texto || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  const idxClave = elegirIndicePalabraClave(palabras);
  const esCrema = tema === "crema";

  const largo = texto.length;
  const fontSize =
    tamanoFuente ?? (largo <= 28 ? 72 : largo <= 48 ? 62 : largo <= 68 ? 54 : 46);

  const frameBase = inicioSeg * fps;
  // Ráfaga total medida en referencias: 9–18 frames para toda la frase (`guia-estilo-video.md` §1).
  const ventanaEntrada = Math.min(11, Math.max(4, palabras.length * 1.6));
  const durPalabra = 7; // Total = 11 + 7 = 18 frames máx, mín = 4 + 7 = 11 frames

  const colorSolido = esCrema ? PALETA.tinta : PALETA.blanco;
  const colorFantasma = esCrema ? "#9c9588" : PALETA.gris;

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        columnGap: 15,
        rowGap: 10,
        fontSize,
        fontWeight: 900,
        lineHeight: 1.1,
        letterSpacing: "-0.03em",
      }}
    >
      {palabras.map((palabra, idx) => {
        const esClave = idx === idxClave;
        // En el gancho las 2 primeras palabras ya están en pantalla en el frame 0 (`guia-estilo-video.md` §2)
        const yaPresente = esGancho && idx < Math.min(2, palabras.length);
        const progresoIdx =
          palabras.length <= 1 ? 0 : idx / Math.max(1, palabras.length - 1);
        const fInicio = yaPresente ? -20 : frameBase + progresoIdx * ventanaEntrada;

        const avance = yaPresente
          ? 1
          : interpolate(frame, [fInicio, fInicio + durPalabra], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.out(Easing.cubic),
            });

        if (avance <= 0.01) return null;

        const subida = yaPresente ? 0 : interpolate(avance, [0, 1], [14, 0]);
        const asentada = yaPresente || frame >= fInicio + durPalabra * 0.55;

        return (
          <span
            key={`${idx}-${palabra}`}
            style={{
              display: "inline-block",
              opacity: Math.min(1, avance * 1.35),
              translate: `0px ${subida.toFixed(1)}px`,
              scale: esClave && asentada ? "1.03" : "1",
              color: esClave && asentada ? PALETA.blanco : asentada ? colorSolido : colorFantasma,
              backgroundColor: esClave && asentada ? PALETA.vino : "transparent",
              padding: esClave ? "2px 15px 5px" : "2px 0",
              borderRadius: esClave ? 11 : 0,
            }}
          >
            {palabra}
          </span>
        );
      })}
    </div>
  );
};

// ------------------------------------------------------------------ construcción de planos y cortes

type SegmentoNarrativo = {
  indice: number;
  tipo: "gancho" | "bloque" | "cierre";
  texto: string;
  etiquetaFase: string;
  subtituloPie: string;
  inicioSeg: number;
  finSeg: number;
  tema: TemaVisual;
  faseEscena: number;
};

const construirSegmentos = (
  gancho: string,
  bloques: string[],
  cierre: string,
  etiquetas: string[],
  duracionTotalSeg: number,
  tiemposBloques?: number[],
  tiempoCierre?: number,
): SegmentoNarrativo[] => {
  const tieneSincronia = Array.isArray(tiemposBloques) && tiemposBloques.length > 0;
  const tFinGancho =
    tieneSincronia && typeof tiemposBloques?.[0] === "number"
      ? Math.max(1.2, tiemposBloques[0])
      : GANCHO_SEG;

  const tCierre =
    typeof tiempoCierre === "number" && tiempoCierre > tFinGancho
      ? tiempoCierre
      : GANCHO_SEG + bloques.length * CADENCIA_SEG;

  const segmentos: SegmentoNarrativo[] = [];

  // Plano 0: Gancho en fondo oscuro
  segmentos.push({
    indice: 0,
    tipo: "gancho",
    texto: gancho,
    etiquetaFase: "EL CONTRASTE",
    subtituloPie: etiquetas[0] || "ANTES VS AHORA",
    inicioSeg: 0,
    finSeg: bloques.length > 0 ? tFinGancho : tCierre,
    tema: "oscuro",
    faseEscena: 0,
  });

  // Planos 1..N: Cada bloque alterna fondo (Crema <-> Oscuro) para cortes limpios y notorios
  bloques.forEach((bloque, i) => {
    const tIni =
      tieneSincronia && typeof tiemposBloques?.[i] === "number"
        ? tiemposBloques[i]
        : tFinGancho + i * CADENCIA_SEG;
    const tFin =
      i + 1 < bloques.length
        ? tieneSincronia && typeof tiemposBloques?.[i + 1] === "number"
          ? tiemposBloques[i + 1]
          : tFinGancho + (i + 1) * CADENCIA_SEG
        : tCierre;

    const mitad = Math.max(1, Math.floor(bloques.length / 2));
    const esLadoA = i < mitad;
    const etiquetaFase = esLadoA ? "ASÍ PASA HOY" : i === bloques.length - 1 ? "RESULTADO" : "EL SISTEMA";
    const subPie =
      etiquetas[Math.min(etiquetas.length - 1, Math.floor((i / Math.max(1, bloques.length)) * etiquetas.length))] ||
      (esLadoA ? "SIN SISTEMA" : "RESUELTO");

    segmentos.push({
      indice: i + 1,
      tipo: "bloque",
      texto: bloque,
      etiquetaFase,
      subtituloPie: subPie,
      inicioSeg: tIni,
      finSeg: Math.max(tIni + 0.6, tFin),
      tema: i % 2 === 0 ? "crema" : "oscuro",
      faseEscena: esLadoA ? 1 : i === bloques.length - 1 ? 3 : 2,
    });
  });

  // Plano final: Cierre (alterna respecto al último plano para marcar remate visual)
  const ultimoTema = segmentos[segmentos.length - 1]?.tema ?? "crema";
  segmentos.push({
    indice: segmentos.length,
    tipo: "cierre",
    texto: cierre,
    etiquetaFase: "SIGUIENTE PASO",
    subtituloPie: "LINK EN BIO",
    inicioSeg: tCierre,
    finSeg: Math.max(tCierre + 1.2, duracionTotalSeg),
    tema: ultimoTema === "oscuro" ? "crema" : "oscuro",
    faseEscena: 3,
  });

  return segmentos;
};

// ------------------------------------------------------------------ componente principal ReelVertical

export const ReelVertical: React.FC<Props> = ({
  gancho,
  bloques,
  cierre,
  nicho = "",
  badge = "",
  escena = "contraste",
  etiquetas = [],
  tiemposBloques,
  tiempoCierre,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const segActual = frame / fps;
  const durTotalSeg = durationInFrames / fps;

  const segmentos = construirSegmentos(
    gancho,
    bloques,
    cierre,
    etiquetas,
    durTotalSeg,
    tiemposBloques,
    tiempoCierre,
  );

  let activo = segmentos[0];
  for (const seg of segmentos) {
    if (segActual >= seg.inicioSeg) {
      activo = seg;
    }
  }

  const durSegmento = Math.max(0.5, activo.finSeg - activo.inicioSeg);
  const tiempoEnSeg = Math.max(0, segActual - activo.inicioSeg);

  // Regla dura `guia-estilo-video.md` §1: ningún plano estático dura más de 3 s (90 frames).
  // Si el segmento supera 2.55 s, divide automáticamente en sub-planos con punch-in seco de cámara.
  const nSubPlanos = Math.max(1, Math.ceil(durSegmento / MAX_PLANO_ESTATICO_SEG));
  const durSubPlano = durSegmento / nSubPlanos;
  const subPlanoIdx = Math.min(nSubPlanos - 1, Math.floor(tiempoEnSeg / durSubPlano));
  const inicioSubPlanoSeg = activo.inicioSeg + subPlanoIdx * durSubPlano;

  // Golpe sutil de asentamiento en cada corte (3 frames) + push-in continuo dentro del sub-plano
  const framesDesdeCorte = Math.max(0, frame - inicioSubPlanoSeg * fps);
  const golpeCorte = interpolate(framesDesdeCorte, [0, 5], [1.035, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  const pushContinuo = interpolate(
    segActual,
    [inicioSubPlanoSeg, inicioSubPlanoSeg + durSubPlano],
    [1.0, 1.045],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const escalaPunchSubPlano = subPlanoIdx % 2 === 1 ? 1.095 : 1.0;
  const escalaEscena = golpeCorte * pushContinuo * escalaPunchSubPlano;
  const desplazamientoEscenaY = subPlanoIdx % 2 === 1 ? -16 : 0;

  const inicioBloques = segmentos[1]?.inicioSeg ?? GANCHO_SEG;
  const inicioCierre = segmentos[segmentos.length - 1]?.inicioSeg ?? durTotalSeg - CIERRE_SEG;
  const cadenciaMedia =
    bloques.length > 0
      ? Math.max(1.3, (inicioCierre - inicioBloques) / Math.max(1, bloques.length))
      : CADENCIA_SEG;

  const badgeTexto = resolverBadge(nicho, badge);
  const esCrema = activo.tema === "crema";
  const colorSecundario = esCrema ? "#5a544b" : "#9a9aa2";
  const progresoGlobal = interpolate(frame, [0, Math.max(1, durationInFrames - 1)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Palabras del subtítulo quemado inferior (`guia-estilo-video.md` §3.7: 2-3 palabras, 1 resaltada)
  const palabrasPie = (activo.subtituloPie || "")
    .trim()
    .toUpperCase()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 4);
  const idxPieClave = elegirIndicePalabraClave(palabrasPie);

  return (
    <AbsoluteFill>
      <FondoConGrilla tema={activo.tema} />

      <AbsoluteFill
        style={{
          paddingTop: SAFE_TOP,
          paddingBottom: SAFE_BOTTOM,
          paddingLeft: SAFE_LEFT,
          paddingRight: SAFE_RIGHT,
          display: "flex",
          flexDirection: "column",
          alignItems: "stretch",
          justifyContent: "space-between",
          fontFamily: FUENTE,
        }}
      >
        {/* ---------------- CABECERA PERSISTENTE ---------------- */}
        <CabeceraPersistente badgeTexto={badgeTexto} tema={activo.tema} />

        {/* ---------------- MITAD SUPERIOR: TITULAR EN RÁFAGA ---------------- */}
        <div
          style={{
            width: ANCHO_UTIL,
            minHeight: 340,
            maxHeight: 450,
            flex: "0 0 auto",
            display: "flex",
            flexDirection: "column",
            justifyContent: "flex-start",
            alignItems: "flex-start",
            overflow: "hidden",
          }}
        >
          {/* Eyebrow editorial de sección */}
          <div
            style={{
              fontSize: 19,
              fontWeight: 800,
              letterSpacing: "0.16em",
              color: PALETA.vino,
              marginBottom: 14,
            }}
          >
            {activo.etiquetaFase}
          </div>

          <FraseEnRafaga
            key={`plano-${activo.indice}`}
            texto={activo.texto}
            inicioSeg={activo.inicioSeg}
            tema={activo.tema}
            esGancho={activo.tipo === "gancho"}
          />
        </div>

        {/* ---------------- MITAD INFERIOR: ESCENA ISOMÉTRICA CON CÁMARA ---------------- */}
        <div
          style={{
            width: ANCHO_UTIL,
            flex: 1,
            minHeight: 540,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: "100%",
              height: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              scale: escalaEscena.toFixed(4),
              translate: `0px ${desplazamientoEscenaY}px`,
            }}
          >
            <EscenaIsometrica
              escena={escena as NombreEscena}
              inicio={inicioBloques}
              cadencia={cadenciaMedia}
              etiquetas={etiquetas}
              tema={activo.tema}
              fase={activo.faseEscena + (subPlanoIdx % 2)}
            />
          </div>
        </div>

        {/* ---------------- PIE QUEMADO EN ZONA SEGURA (`guia-estilo-video.md` §3.7) ---------------- */}
        <div
          style={{
            width: ANCHO_UTIL,
            flex: "0 0 auto",
            paddingTop: 12,
            display: "flex",
            flexDirection: "column",
            gap: 14,
          }}
        >
          <div
            style={{
              display: "flex",
              flexDirection: "row",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              {palabrasPie.map((pal, idx) => {
                const resaltada = idx === idxPieClave;
                return (
                  <span
                    key={`pie-${idx}-${pal}`}
                    style={{
                      fontSize: 24,
                      fontWeight: 900,
                      letterSpacing: "0.06em",
                      color: resaltada
                        ? PALETA.blanco
                        : esCrema
                          ? PALETA.tinta
                          : PALETA.blanco,
                      backgroundColor: resaltada ? PALETA.vino : "transparent",
                      padding: resaltada ? "4px 12px" : "4px 0",
                      borderRadius: resaltada ? 7 : 0,
                    }}
                  >
                    {pal}
                  </span>
                );
              })}
            </div>

            <span
              style={{
                fontSize: 20,
                fontWeight: 700,
                letterSpacing: "0.04em",
                color: colorSecundario,
              }}
            >
              {activo.tipo === "cierre" ? "ESCRÍBENOS HOY" : "CUÉNTANOS TU PROBLEMA"}
            </span>
          </div>

          {/* Barra de ritmo sutil (cero números) */}
          <div
            style={{
              width: "100%",
              height: 5,
              borderRadius: 999,
              backgroundColor: esCrema ? "rgba(10,10,10,0.12)" : "rgba(255,255,255,0.12)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${(progresoGlobal * 100).toFixed(1)}%`,
                height: "100%",
                backgroundColor: PALETA.vino,
              }}
            />
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
