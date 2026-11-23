import { Composition } from "remotion";
import { LogoFrase, logoFraseSchema } from "./LogoFrase";
import { LogoSaludo } from "./LogoSaludo";

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
