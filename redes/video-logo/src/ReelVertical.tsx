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
} from "./EscenasIsometricas";

/**
 * Plantilla vertical 1080x1920 @ 30fps para Reels de El Socio.
 *
 * Aplica lo medido en `contexto/guia-estilo-video.md`:
 *  - Gancho presente desde el frame 1 (sin calentamiento).
 *  - Un bloque de texto cada ~2 s (60 frames), nunca más de 3 s.
 *  - El texto se ACUMULA: las palabras anteriores se quedan en pantalla.
 *  - Cada palabra entra con "estado fantasma": gris primero, blanco al asentar.
 *  - Push-in lento y constante de cámara sobre fondo fijo.
 *  - TEXTO ARRIBA, ESCENA ISOMÉTRICA ABAJO (§3.1): el texto nunca cae sobre el
 *    centro de interés, y la escena es el único elemento héroe de la pieza.
 *  - Fondo con grilla sutil, paleta de El Socio. Cero cifras en el componente.
 */

export const reelVerticalSchema = z.object({
  gancho: z.string(),
  bloques: z.array(z.string()),
  cierre: z.string(),
  // Opcionales: las piezas viejas (y `content_manager.py` antes de este paso) no los mandan.
  escena: z.enum(NOMBRES_ESCENA).optional(),
  etiquetas: z.array(z.string()).optional(),
  // Tiempos exactos medidos por `voice_engine.py` para sincronía milimétrica voz <-> subtítulo.
  tiemposBloques: z.array(z.number()).optional(),
  tiempoCierre: z.number().optional(),
  duracionFrames: z.number().optional(),
});

type Props = z.infer<typeof reelVerticalSchema>;

// Zonas seguras de Reels (convención de la plataforma, ver guía §5).
const SAFE_TOP = 220;
const SAFE_BOTTOM = 380;
const SAFE_LEFT = 80;
/** La columna de botones de Reels vive aquí: nada de contenido a la derecha de esto. */
const SAFE_RIGHT = 160;

/**
 * El push-in escala TODO el encuadre, así que el contenido tiene que empezar más adentro
 * que la zona segura o al final del video se sale por arriba. Este colchón es la cuenta:
 * con 1200x720 de caja y 1.05 de escala, el máximo cae justo dentro de la zona segura.
 */
const COLCHON_PUSH = 60;
const PUSH_MAX = 1.05;
const DERIVA_MAX = -20;

const ANCHO_CAJA = 1080 - SAFE_LEFT - SAFE_RIGHT - 2 * COLCHON_PUSH; // 720
const ALTO_CAJA = 1920 - SAFE_TOP - SAFE_BOTTOM - 2 * COLCHON_PUSH; // 1200
/** Mitad superior para el texto, mitad inferior para la escena, cierre quemado al pie. */
const ALTO_TEXTO = 600;
const ALTO_CIERRE = 110;

const TINTA = PALETA.tinta;
const BLANCO = PALETA.blanco;
const FANTASMA = PALETA.gris;
const VINO = PALETA.vino;

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
        marginRight: 16,
        opacity: avance,
        translate: `0px ${subida}px`,
        color: asentado > 0.5 ? BLANCO : FANTASMA,
        background: resaltada && asentado > 0.5 ? VINO : "transparent",
        padding: resaltada ? "0 12px" : undefined,
        borderRadius: resaltada ? 8 : undefined,
      }}
    >
      {texto}
    </span>
  );
};

// Tiempos del guion, en segundos. Salen de la cadencia medida en la guía (§1).
export const GANCHO_SEG = 2;
export const CADENCIA_SEG = 2;
export const CIERRE_SEG = 3;

/** Duración exacta del reel según cuántos bloques trae el guion: sin cola muerta. */
export const duracionEnFrames = (nBloques: number, fps = 30): number =>
  Math.round((GANCHO_SEG + Math.max(0, nBloques) * CADENCIA_SEG + CIERRE_SEG) * fps);

export const ReelVertical: React.FC<Props> = ({
  gancho,
  bloques,
  cierre,
  escena = "contraste",
  etiquetas = [],
  tiemposBloques,
  tiempoCierre,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Push-in lento y constante: lo que separa "presentación" de "video producido".
  const escala = interpolate(frame, [0, durationInFrames], [1, PUSH_MAX], {
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.quad),
  });
  const deriva = interpolate(frame, [0, durationInFrames], [0, DERIVA_MAX], {
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.quad),
  });

  // Si viene locución medida por `voice_engine.py`, cada bloque entra al milisegundo
  // exacto en que habla la voz; si no, usa la cadencia fija de 2 s de la guía.
  const tieneSincronia = Array.isArray(tiemposBloques) && tiemposBloques.length > 0;
  const inicioBloques =
    tieneSincronia && typeof tiemposBloques?.[0] === "number" ? tiemposBloques[0] : GANCHO_SEG;
  const inicioCierre =
    typeof tiempoCierre === "number" && tiempoCierre > 0
      ? tiempoCierre
      : GANCHO_SEG + bloques.length * CADENCIA_SEG;
  const cadencia =
    tieneSincronia && bloques.length > 0
      ? Math.max(1.4, (inicioCierre - inicioBloques) / Math.max(1, bloques.length))
      : CADENCIA_SEG;

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
          paddingTop: SAFE_TOP + COLCHON_PUSH,
          paddingBottom: SAFE_BOTTOM + COLCHON_PUSH,
          paddingLeft: SAFE_LEFT + COLCHON_PUSH,
          paddingRight: SAFE_RIGHT + COLCHON_PUSH,
          flexDirection: "column",
          alignItems: "stretch",
          justifyContent: "flex-start",
          fontFamily: FUENTE,
        }}
      >
        {/* ---------------- mitad superior: solo texto ---------------- */}
        <div
          style={{
            width: ANCHO_CAJA,
            // Ocupa lo que necesite hasta su tope; el aire sobrante se lo queda la escena,
            // que lo reparte arriba y abajo. Un guion largo se recorta aquí antes que
            // invadir la mitad inferior.
            flex: "0 0 auto",
            maxHeight: ALTO_TEXTO,
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-start",
            justifyContent: "flex-start",
          }}
        >
          {/* Gancho: presente desde el frame 1, el bloque de texto más grande. */}
          <div
            style={{
              fontSize: 72,
              fontWeight: 800,
              lineHeight: 1.08,
              letterSpacing: "-0.02em",
              color: BLANCO,
            }}
          >
            {gancho}
          </div>

          {/* Bloques acumulativos: lo anterior NO se borra. */}
          <div
            style={{
              marginTop: 34,
              fontSize: 44,
              fontWeight: 700,
              lineHeight: 1.32,
              letterSpacing: "-0.01em",
            }}
          >
            {bloques.map((bloque, i) => {
              const tMedido = tiemposBloques?.[i];
              return (
                <Palabra
                  key={`${i}-${bloque}`}
                  texto={bloque}
                  entraEn={typeof tMedido === "number" ? tMedido : GANCHO_SEG + i * CADENCIA_SEG}
                  resaltada={i === bloques.length - 1}
                />
              );
            })}
          </div>
        </div>

        {/* ---------------- mitad inferior: la escena isométrica ---------------- */}
        <div
          style={{
            width: ANCHO_CAJA,
            flex: 1,
            minHeight: ALTO_CAJA - ALTO_TEXTO - ALTO_CIERRE,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <EscenaIsometrica
            escena={escena as NombreEscena}
            inicio={inicioBloques}
            cadencia={cadencia}
            etiquetas={etiquetas}
          />
        </div>

        {/* ---------------- cierre quemado al pie (guía §3.7) ---------------- */}
        <div
          style={{
            width: ANCHO_CAJA,
            flex: "0 0 auto",
            height: ALTO_CIERRE,
            display: "flex",
            alignItems: "flex-end",
          }}
        >
          {cierreVisible ? (
            <div
              style={{
                fontSize: 40,
                fontWeight: 600,
                color: BLANCO,
                opacity: cierreAvance,
                translate: `0px ${interpolate(cierreAvance, [0, 1], [16, 0])}px`,
              }}
            >
              {cierre}
            </div>
          ) : null}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
