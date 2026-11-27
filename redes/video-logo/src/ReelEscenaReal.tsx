import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { FUENTE, SAFE_BOTTOM, segmentoEn, segmentosReel, tiemposPalabras, type PropsReel } from "./comun";
import { MUNDO } from "./mundo/base";
import { Socio, type PoseSocio } from "./Socio";

/**
 * PROTOTIPO — "escena real": una FOTO de fondo y el personaje de la marca encima.
 *
 * Es la estructura del reel que aprobó Raymond (el de ramiro.cubria, guía §15.2): ellos no
 * dibujaron el Ferrari ni el banco ni la cocina; pusieron metraje real de fondo y encima un
 * personaje de dibujo. Su personaje es MÁS simple que el nuestro y el conjunto se ve mejor,
 * porque el detalle lo aporta el fondo.
 *
 * Qué resuelve, que el motor isométrico no puede:
 *  - Escenarios: un parque, un carro, una empresa, alguien paseando el perro... son fotos, no
 *    6.000 líneas de SVG dibujadas a mano.
 *  - Calidad: fotografía profesional en vez del techo de mi ilustración.
 *  - Variedad: cada reel puede tener un fondo distinto sin tocar código.
 *
 * El fondo de ESTA demo sale de un fotograma de las referencias de Raymond: sirve para ver el
 * concepto, NO para publicar. En producción vendría de un banco de fotos con licencia libre.
 */

const POSE_POR_TIPO: Record<string, PoseSocio> = {
  gancho: "senala",
  bloque: "habla",
  cierre: "celebra",
};

export const ReelEscenaReal: React.FC<PropsReel & { fondos?: string[] }> = (props) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const { segmentos } = segmentosReel(props, durationInFrames / fps);
  const seg = frame / fps;
  const actual = segmentos[segmentoEn(segmentos, seg)] ?? segmentos[0];
  const fondos = props.fondos?.length ? props.fondos : ["fondos/demo_ciudad.jpg"];
  const fondo = fondos[Math.min(fondos.length - 1, Math.floor(actual.indice / 2))];

  // La cámara no se detiene nunca (guía §15, regla 1): un lento acercamiento al fondo.
  const t = interpolate(frame, [0, durationInFrames], [0, 1]);
  const zoomFondo = 1.06 + t * 0.1;
  const desliza = interpolate(t, [0, 1], [0, -26]);

  // Subtítulo palabra por palabra, discreto y abajo (regla 5 de §15).
  const palabras = actual.texto.trim().split(/\s+/).filter(Boolean);
  const voz = tiemposPalabras(palabras, actual.inicio * fps, actual.fin * fps);
  let sonando = -1;
  for (let i = 0; i < voz.length; i++) if (frame >= voz[i]) sonando = i;

  const pose = POSE_POR_TIPO[actual.tipo] ?? "habla";
  const entra = interpolate(frame - actual.inicio * fps, [0, 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: "#111", fontFamily: FUENTE, overflow: "hidden" }}>
      {/* capa 1: la foto, con su propio movimiento */}
      <AbsoluteFill style={{ transform: `scale(${zoomFondo}) translateY(${desliza}px)` }}>
        <Img src={staticFile(fondo)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      </AbsoluteFill>

      {/* capa 2: oscurecido abajo para que el personaje y el texto se lean sobre cualquier foto */}
      <AbsoluteFill
        style={{ background: "linear-gradient(180deg, rgba(0,0,0,0.12) 0%, rgba(0,0,0,0.05) 42%, rgba(0,0,0,0.72) 100%)" }}
      />

      {/* capa 3: el personaje de la marca, grande y actuando */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: SAFE_BOTTOM - 90,
          display: "flex",
          justifyContent: "center",
          opacity: Math.min(1, entra * 1.4),
          transform: `translateY(${(1 - entra) * 40}px)`,
        }}
      >
        <Socio alto={1060} pose={pose} />
      </div>

      {/* capa 4: subtítulo por palabra */}
      <div
        style={{
          position: "absolute",
          left: 60,
          right: 60,
          bottom: SAFE_BOTTOM + 40,
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          gap: "10px 14px",
        }}
      >
        {palabras.map((p: string, i: number) => (
          <span
            key={i}
            style={{
              fontSize: 56,
              fontWeight: 900,
              letterSpacing: "-0.02em",
              color: i === sonando ? "#ffffff" : "rgba(255,255,255,0.74)",
              backgroundColor: i === sonando ? MUNDO.vino : "transparent",
              padding: i === sonando ? "2px 12px" : "2px 0",
              borderRadius: 8,
              textShadow: "0 3px 10px rgba(0,0,0,0.8)",
            }}
          >
            {p}
          </span>
        ))}
      </div>
    </AbsoluteFill>
  );
};
