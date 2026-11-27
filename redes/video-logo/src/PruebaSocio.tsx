import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { FUENTE } from "./comun";
import { MUNDO } from "./mundo/base";
import { Socio, type PoseSocio } from "./Socio";

/**
 * Banco de pruebas del personaje. No es un formato: sirve para juzgar al Socio actuando, grande y
 * de frente, antes de rehacer ningún reel con él. Cada pose dura 2 s.
 */

const POSES: { pose: PoseSocio; etiqueta: string }[] = [
  { pose: "habla", etiqueta: "HABLA" },
  { pose: "senala", etiqueta: "SEÑALA" },
  { pose: "piensa", etiqueta: "PIENSA" },
  { pose: "camina", etiqueta: "CAMINA" },
  { pose: "celebra", etiqueta: "CELEBRA" },
];

export const PruebaSocio: React.FC = () => {
  const frame = useCurrentFrame();
  const i = Math.min(POSES.length - 1, Math.floor(frame / 60));
  const actual = POSES[i];
  return (
    <AbsoluteFill style={{ backgroundColor: "#2a2228" }}>
      {/* pared sobria, sin HUD ni neón (guía §4) */}
      <AbsoluteFill style={{ background: "linear-gradient(180deg,#3a2f36 0%,#241c21 100%)" }} />
      <div style={{ position: "absolute", left: 0, right: 0, top: 150, textAlign: "center", fontFamily: FUENTE, fontWeight: 900, fontSize: 64, color: "#f3ead7" }}>
        {actual.etiqueta}
      </div>
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 300, display: "flex", justifyContent: "center", alignItems: "flex-end" }}>
        <Socio alto={1180} pose={actual.pose} />
      </div>
      {/* suelo */}
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 330, backgroundColor: MUNDO.vinoOscuro, opacity: 0.55 }} />
    </AbsoluteFill>
  );
};
