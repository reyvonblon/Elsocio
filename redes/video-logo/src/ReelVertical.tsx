import { z } from "zod";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

/**
 * Plantilla vertical 1080x1920 @ 30fps para Reels de El Socio.
 *
 * Aplica lo medido en `contexto/guia-estilo-video.md`:
 *  - Gancho presente desde el frame 1 (sin calentamiento).
 *  - Un bloque de texto cada ~2 s (60 frames), nunca más de 3 s.
 *  - El texto se ACUMULA: las palabras anteriores se quedan en pantalla.
 *  - Cada palabra entra con "estado fantasma": gris primero, blanco al asentar.
 *  - Push-in lento y constante de cámara sobre fondo fijo.
 *  - Un solo elemento héroe animado por escena (la línea que se dibuja).
 *  - Fondo con grilla sutil, paleta de El Socio. Cero cifras en el componente.
 */

export const reelVerticalSchema = z.object({
  gancho: z.string(),
  bloques: z.array(z.string()),
  cierre: z.string(),
});

type Props = z.infer<typeof reelVerticalSchema>;

// Zonas seguras de Reels (convención de la plataforma, ver guía §6).
const SAFE_TOP = 220;
const SAFE_BOTTOM = 380;

const TINTA = "#0a0a0a";
const BLANCO = "#ffffff";
const FANTASMA = "#6e6e73";
const VINO = "#9c1c2e";

const FUENTE =
  "-apple-system,BlinkMacSystemFont,'SF Pro Text','Segoe UI',Helvetica,Arial,sans-serif";

/** Grilla de puntos sutil. Fija, no se anima: el movimiento lo pone la cámara. */
const Grilla: React.FC = () => (
  <AbsoluteFill
    style={{
      backgroundImage: `radial-gradient(${"#ffffff"}14 1.5px, transparent 1.5px)`,
      backgroundSize: "48px 48px",
    }}
  />
);

/**
 * Una palabra con estado fantasma: entra en gris y se asienta en blanco.
 * No es un fade de opacidad — es el cambio de color lo que lee como "diseñado".
 */
const Palabra: React.FC<{ texto: string; entraEn: number; resaltada?: boolean }> = ({
  texto,
  entraEn,
  resaltada = false,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const inicio = entraEn * fps;

  // 9-18 frames de entrada, como las ráfagas medidas en las referencias.
  const avance = interpolate(frame, [inicio, inicio + 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  const subida = interpolate(avance, [0, 1], [14, 0]);
  // El color va de fantasma a definitivo en la segunda mitad de la entrada.
  const asentado = interpolate(frame, [inicio + 6, inicio + 16], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  if (frame < inicio) return null;

  return (
    <span
      style={{
        display: "inline-block",
        marginRight: 18,
        opacity: avance,
        translate: `0px ${subida}px`,
        color: asentado > 0.5 ? BLANCO : FANTASMA,
        background: resaltada && asentado > 0.5 ? VINO : "transparent",
        padding: resaltada ? "0 14px" : undefined,
        borderRadius: resaltada ? 8 : undefined,
      }}
    >
      {texto}
    </span>
  );
};

/** Elemento héroe: una línea que se dibuja sola. Uno por escena, nunca dos. */
const LineaHeroe: React.FC<{ entraEn: number }> = ({ entraEn }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const trazo = interpolate(frame, [entraEn * fps, (entraEn + 0.8) * fps], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

  return (
    <svg width={720} height={120} viewBox="0 0 720 120" style={{ marginTop: 40 }}>
      <path
        d="M 20 80 C 180 20, 420 110, 700 40"
        fill="none"
        stroke={VINO}
        strokeWidth={10}
        strokeLinecap="round"
        pathLength={1}
        strokeDasharray={1}
        strokeDashoffset={trazo}
      />
    </svg>
  );
};

// Tiempos del guion, en segundos. Salen de la cadencia medida en la guía (§1).
export const GANCHO_SEG = 2;
export const CADENCIA_SEG = 2;
export const CIERRE_SEG = 3;

/** Duración exacta del reel según cuántos bloques trae el guion: sin cola muerta. */
export const duracionEnFrames = (nBloques: number, fps = 30): number =>
  Math.round((GANCHO_SEG + Math.max(0, nBloques) * CADENCIA_SEG + CIERRE_SEG) * fps);

export const ReelVertical: React.FC<Props> = ({ gancho, bloques, cierre }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Push-in lento y constante: lo que separa "presentación" de "video producido".
  const escala = interpolate(frame, [0, durationInFrames], [1, 1.08], {
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.quad),
  });
  const deriva = interpolate(frame, [0, durationInFrames], [0, -26], {
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.quad),
  });

  // Un bloque cada 2 s, empezando después del gancho. El gancho está desde el frame 1.
  const inicioBloques = GANCHO_SEG;
  const cadencia = CADENCIA_SEG;
  const inicioCierre = inicioBloques + bloques.length * cadencia;

  const cierreVisible = frame >= inicioCierre * fps;
  const cierreAvance = interpolate(
    frame,
    [inicioCierre * fps, (inicioCierre + 0.5) * fps],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) },
  );

  return (
    <AbsoluteFill style={{ backgroundColor: TINTA }}>
      <Grilla />
      <AbsoluteFill
        style={{
          scale: String(escala),
          translate: `0px ${deriva}px`,
          paddingTop: SAFE_TOP,
          paddingBottom: SAFE_BOTTOM,
          paddingLeft: 80,
          paddingRight: 80,
          alignItems: "flex-start",
          // Centrado mientras no haya ilustración isométrica abajo. Cuando la haya,
          // esto vuelve a "flex-start" y la escena ocupa la mitad inferior (guía §4.1).
          justifyContent: "center",
          fontFamily: FUENTE,
        }}
      >
        {/* Gancho: presente desde el frame 1, el bloque de texto más grande. */}
        <div
          style={{
            fontSize: 84,
            fontWeight: 800,
            lineHeight: 1.12,
            letterSpacing: "-0.02em",
            color: BLANCO,
            maxWidth: 900,
          }}
        >
          {gancho}
        </div>

        <LineaHeroe entraEn={1.2} />

        {/* Bloques acumulativos: lo anterior NO se borra. */}
        <div
          style={{
            marginTop: 30,
            fontSize: 58,
            fontWeight: 700,
            lineHeight: 1.35,
            letterSpacing: "-0.01em",
            maxWidth: 900,
          }}
        >
          {bloques.map((bloque, i) => (
            <Palabra
              key={`${i}-${bloque}`}
              texto={bloque}
              entraEn={inicioBloques + i * cadencia}
              resaltada={i === bloques.length - 1}
            />
          ))}
        </div>

        {/* Cierre seco. */}
        {cierreVisible ? (
          <div
            style={{
              marginTop: 48,
              fontSize: 46,
              fontWeight: 600,
              color: BLANCO,
              opacity: cierreAvance,
              translate: `0px ${interpolate(cierreAvance, [0, 1], [16, 0])}px`,
            }}
          >
            {cierre}
          </div>
        ) : null}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
