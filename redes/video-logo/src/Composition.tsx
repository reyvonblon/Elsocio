import { Composition } from "remotion";
import { PruebaSocio } from "./PruebaSocio";
import { ReelEscenaReal } from "./ReelEscenaReal";
import { HistoriaVertical, historiaVerticalSchema } from "./HistoriaVertical";
import { CarruselLaminas, carruselLaminasSchema, duracionCarrusel } from "./CarruselLaminas";
import { LogoFrase, logoFraseSchema } from "./LogoFrase";
import { LogoSaludo } from "./LogoSaludo";
import { ReelVertical, duracionEnFrames, reelVerticalSchema } from "./ReelVertical";
import { ReelMundo, duracionReelMundo, reelMundoSchema } from "./ReelMundo";
import { ReelAuto } from "./ReelAuto";
import { duracionReel, reelSchema } from "./comun";

export const MyComposition = () => {
  return (
    <>
      <Composition
        id="LogoFrase"
        component={LogoFrase}
        durationInFrames={120}
        fps={30}
        width={1080}
        height={1350}
        schema={logoFraseSchema}
        defaultProps={{
          frase: "El taller te entregó algo distinto a lo que pediste. Otra vez.",
        }}
      />
      <Composition
        id="HistoriaVertical"
        component={HistoriaVertical}
        durationInFrames={30}
        fps={30}
        width={1080}
        height={1920}
        schema={historiaVerticalSchema}
        defaultProps={{
          gancho: "Tu inventario lleva semanas esperando una foto decente.",
          subtexto: "Cada lanzamiento se frena por coordinar estudio y modelos.",
          cierre: "Responde esta historia con tu caso",
          badge: "CATÁLOGO",
          tema: "oscuro" as const,
        }}
      />
      {/* Carrusel de Instagram: un frame = una lámina (generar_carrusel.sh). */}
      <Composition
        id="CarruselLaminas"
        component={CarruselLaminas}
        durationInFrames={duracionCarrusel({ laminas: new Array(5).fill("") })}
        fps={30}
        calculateMetadata={({ props }) => ({ durationInFrames: duracionCarrusel(props) })}
        width={1080}
        height={1350}
        schema={carruselLaminasSchema}
        defaultProps={{
          laminas: [
            "Tu taller no se equivoca. Le estás mandando audios.",
            "Cada colección arranca con notas de voz, fotos borrosas y medidas al ojo.",
            "El patronista adivina, la muestra sale mal y toca repetirla.",
            "Una ficha técnica clara cambia eso: medidas, materiales y costuras en un solo plano.",
            "Escríbenos tu caso por mensaje directo",
          ],
          badge: "CONFECCIÓN",
          tema: "oscuro" as const,
        }}
      />
      <Composition
        id="ReelVertical"
        component={ReelVertical}
        durationInFrames={duracionEnFrames(6)}
        fps={30}
        calculateMetadata={({ props }) => ({
          durationInFrames:
            props.duracionFrames && props.duracionFrames > 0
              ? props.duracionFrames
              : duracionEnFrames(props.bloques?.length ?? 6),
        })}
        width={1080}
        height={1920}
        schema={reelVerticalSchema}
        defaultProps={{
          gancho: "Dos talleres reciben la misma colección de ropa.",
          bloques: [
            "Uno recibe audios sueltos y fotos borrosas.",
            "El patronista adivina medidas y repite muestras.",
            "El otro recibe una ficha técnica exacta.",
            "Primero entregas tu idea y tus referencias.",
            "Nosotros armamos el plano técnico listo para corte.",
            "La producción sale bien desde la primera muestra.",
          ],
          nicho: "fichas-tecnicas-ropa",
          escena: "contraste" as const,
          etiquetas: ["A CIEGAS", "FICHA EXACTA", "ENTREGA CLARA", "APROBADO"],
          cierre: "Cuéntanos tu problema · link en bio",
        }}
      />
      {/* Composición que usa generar_video.sh: elige el formato (mundo / collage / duelo) por props.formato. */}
      <Composition
        id="EscenaReal"
        component={ReelEscenaReal}
        durationInFrames={duracionReel({ bloques: new Array(6).fill("") })}
        fps={30}
        width={1080}
        height={1920}
        calculateMetadata={({ props }) => ({ durationInFrames: duracionReel(props) })}
        defaultProps={{ gancho: "", bloques: [], cierre: "" } as never}
      />
      <Composition
        id="PruebaSocio"
        component={PruebaSocio}
        durationInFrames={300}
        fps={30}
        width={1080}
        height={1920}
      />
      <Composition
        id="Reel"
        component={ReelAuto}
        durationInFrames={duracionReel({ bloques: new Array(6).fill("") })}
        fps={30}
        calculateMetadata={({ props }) => ({ durationInFrames: duracionReel(props) })}
        width={1080}
        height={1920}
        schema={reelSchema}
        defaultProps={{
          formato: "collage",
          gancho: "Uno de estos dos talleres te va a arruinar la colección.",
          bloques: [
            "Uno recibe audios sueltos y fotos borrosas.",
            "El patronista adivina medidas y repite muestras.",
            "El lote llega y no es lo que pediste.",
            "El otro recibe una ficha técnica exacta.",
            "Las máquinas cosen sin adivinar nada.",
            "El lote sale igual a lo que pediste.",
          ],
          cierre: "No seas el Taller A. Sé el Taller B. Con El Socio, te lo solucionamos.",
          nicho: "fichas-tecnicas-ropa",
        }}
      />
      {/* Motor Mundo directo: mundo isométrico continuo + cámara que muestra lo que dice la voz. */}
      <Composition
        id="ReelMundo"
        component={ReelMundo}
        durationInFrames={duracionReelMundo({ bloques: new Array(6).fill("") })}
        fps={30}
        calculateMetadata={({ props }) => ({ durationInFrames: duracionReelMundo(props) })}
        width={1080}
        height={1920}
        schema={reelMundoSchema}
        defaultProps={{
          gancho: "Dos talleres reciben la misma colección.",
          bloques: [
            "Uno recibe audios sueltos y fotos borrosas.",
            "El patronista adivina medidas y repite muestras.",
            "El lote llega y no es lo que pediste.",
            "El otro recibe una ficha técnica exacta.",
            "Las máquinas cosen sin adivinar nada.",
            "El lote sale igual a lo que pediste.",
          ],
          cierre: "Cuéntanos tu problema",
          nicho: "fichas-tecnicas-ropa",
          etiquetas: ["A CIEGAS", "Ficha exacta", "Aprobado"],
        }}
      />
      <Composition
        id="LogoSaludo"
        component={LogoSaludo}
        durationInFrames={96}
        fps={30}
        width={1080}
        height={1080}
      />
    </>
  );
};
