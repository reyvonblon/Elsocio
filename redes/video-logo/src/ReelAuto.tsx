import React from "react";
import { ReelCollage } from "./ReelCollage";
import { ReelDuelo } from "./ReelDuelo";
import { ReelMundo } from "./ReelMundo";
import type { PropsReel } from "./comun";

/**
 * Composición única de Reels: elige el formato según `props.formato` ("mundo", "collage", "duelo").
 * El cerebro de contenido rota los formatos; todos comparten voz, tiempos y cierre de venta.
 */
export const ReelAuto: React.FC<PropsReel> = (props) => {
  const formato = (props.formato || "mundo").toLowerCase();
  if (formato === "collage") return <ReelCollage {...props} />;
  if (formato === "duelo") return <ReelDuelo {...props} />;
  return <ReelMundo {...props} />;
};
