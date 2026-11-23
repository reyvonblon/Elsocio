import { Composition } from "remotion";
import { LogoFrase, logoFraseSchema } from "./LogoFrase";
import { LogoSaludo } from "./LogoSaludo";
import { ReelVertical, duracionEnFrames, reelVerticalSchema } from "./ReelVertical";

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
        id="ReelVertical"
        component={ReelVertical}
        durationInFrames={duracionEnFrames(3)}
        fps={30}
        calculateMetadata={({ props }) => ({
          durationInFrames: duracionEnFrames(props.bloques?.length ?? 3),
        })}
        width={1080}
        height={1920}
        schema={reelVerticalSchema}
        defaultProps={{
          gancho: "El taller te entregó algo distinto a lo que pediste.",
          bloques: ["Otra vez.", "No fue mala suerte.", "Fue la ficha técnica."],
          cierre: "Cuéntanos tu problema · link en bio",
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
