import React from "react";
import { AbsoluteFill } from "remotion";
import { FUENTE } from "./comun";
import { aFranjas, caja, rejilla, type Camara, type Rejilla } from "./pixel/lienzo";
import { dibujarHabitacion, type Habitacion } from "./pixel/escena";
import { ARBOL, ARBUSTO, CLIENTE, MATA, PERCHA, SOCIO } from "./pixel/sprites";

/**
 * BANCO DE PRUEBAS — pixel art isométrico (idea de Raymond, 2026-11-27).
 *
 * No es un formato todavía. Sirve para decidir una sola cosa antes de construir nada:
 * ¿el personaje y el mundo en pixel art pasan el filtro de calidad que el SVG no pasó?
 *
 * Tres vistas, que responden tres dudas distintas:
 *  - `taller`: ¿se ve bien una habitación entera? (el plano más usado de la serie)
 *  - `cerca`:  ¿se puede cumplir la regla 2 de §15 (sujeto al 50-70% del cuadro)?
 *              En pixel art ampliar no cuesta dibujo nuevo: son píxeles más grandes, y eso
 *              es estilo correcto, no un defecto. Esto el SVG no lo podía dar.
 *  - `parque`: ¿un escenario nuevo es dato o es código? Exterior, cero paredes, misma máquina.
 */

const LOGICO_W = 135;
const LOGICO_H = 240;
const FONDO = "#141017";

// ---------------------------------------------------------------- escenarios (puro dato)

const TALLER: Habitacion = {
  nombre: "taller de confección",
  ti: 5,
  tj: 5,
  pisoA: "#d8ccb2",
  pisoB: "#c4b596",
  paredIzq: "#cdc1a6",
  paredDer: "#e3dac4",
  altoPared: 72,
  ventanas: [{ pared: "der", desde: 2.7, hasta: 4.5, z0: 30, z1: 62 }],
  muebles: [
    { tipo: "tapete", i: 1.4, j: 2.1, wi: 2.9, wj: 2.0, color: "#8d2435" },
    // mesa de corte larga contra la pared izquierda, con tela encima y la máquina de coser
    { tipo: "cubo", i: 0.2, j: 0.6, wi: 1.0, wj: 2.4, alto: 13, mat: "madera" },
    { tipo: "cubo", i: 0.35, j: 0.75, wi: 0.7, wj: 0.9, alto: 3, mat: "blanco", base: 13 },
    { tipo: "cubo", i: 0.35, j: 1.75, wi: 0.7, wj: 0.3, alto: 2, mat: "vino", base: 13 },
    { tipo: "cubo", i: 0.35, j: 2.15, wi: 0.6, wj: 0.65, alto: 4, mat: "tinta", base: 13 },
    { tipo: "cubo", i: 0.4, j: 2.2, wi: 0.45, wj: 0.16, alto: 5, mat: "tinta", base: 17 },
    // repisa baja contra la pared derecha, con cajas de lote
    { tipo: "cubo", i: 2.9, j: 0.2, wi: 1.7, wj: 0.5, alto: 22, mat: "maderaOscura" },
    { tipo: "cubo", i: 3.0, j: 0.28, wi: 0.55, wj: 0.34, alto: 7, mat: "carton", base: 22 },
    { tipo: "cubo", i: 3.72, j: 0.28, wi: 0.55, wj: 0.34, alto: 10, mat: "carton", base: 22 },
    { tipo: "sprite", sprite: PERCHA, i: 0.85, j: 3.35, escala: 1 },
    { tipo: "sprite", sprite: MATA, i: 4.6, j: 3.5, escala: 1 },
    // los dos personajes
    { tipo: "sprite", sprite: CLIENTE, i: 4.1, j: 1.9, escala: 1 },
    { tipo: "sprite", sprite: SOCIO, i: 2.7, j: 3.2, escala: 1 },
  ],
};

const PARQUE: Habitacion = {
  nombre: "parque",
  ti: 6,
  tj: 6,
  exterior: true,
  pisoA: "#8fa273",
  pisoB: "#7d9163",
  muebles: [
    // sendero en diagonal
    { tipo: "tapete", i: 0, j: 2.1, wi: 6, wj: 1.3, color: "#c9c2ae" },
    // banca
    { tipo: "cubo", i: 4.1, j: 4.0, wi: 1.5, wj: 0.5, alto: 7, mat: "madera" },
    { tipo: "cubo", i: 4.1, j: 3.95, wi: 1.5, wj: 0.15, alto: 15, mat: "maderaOscura" },
    { tipo: "sprite", sprite: ARBOL, i: 0.7, j: 0.5, escala: 2 },
    { tipo: "sprite", sprite: ARBOL, i: 4.4, j: 0.4, escala: 1 },
    { tipo: "sprite", sprite: ARBUSTO, i: 0.4, j: 4.6, escala: 1 },
    { tipo: "sprite", sprite: ARBUSTO, i: 5.3, j: 1.4, escala: 1 },
    { tipo: "sprite", sprite: CLIENTE, i: 3.3, j: 2.4, escala: 1, espejo: true },
    { tipo: "sprite", sprite: SOCIO, i: 1.9, j: 2.7, escala: 1 },
  ],
};

// ---------------------------------------------------------------- vistas

type Vista = "taller" | "cerca" | "parque";

const CAMARAS: Record<Vista, { hab: Habitacion; cam: Camara; cielo?: boolean }> = {
  taller: { hab: TALLER, cam: { tw: 26, ox: 67, oy: 120 } },
  // mismo cuarto, baldosa al doble y centrada en el Socio: primer plano sin dibujar nada nuevo
  cerca: { hab: TALLER, cam: { tw: 52, ox: 80, oy: 72 } },
  parque: { hab: PARQUE, cam: { tw: 24, ox: 67, oy: 108 }, cielo: true },
};

const ESCALA_SPRITE: Record<Vista, number> = { taller: 1, cerca: 2, parque: 1 };

const construir = (vista: Vista): Rejilla => {
  const g = rejilla(LOGICO_W, LOGICO_H);
  const { hab, cam, cielo } = CAMARAS[vista];

  if (cielo) {
    // cielo en bandas: en pixel art un degradado se hace a escalones, y se ve mejor así
    const bandas = ["#262740", "#32324a", "#3f3c54", "#4d455d", "#5c4e64", "#6c576a", "#7d6070", "#8e6a74", "#9e7676", "#ad8279"];
    const altoBanda = Math.ceil(172 / bandas.length);
    bandas.forEach((c, k) => caja(g, 0, k * altoBanda, LOGICO_W, altoBanda, c));
  }

  const escala = ESCALA_SPRITE[vista];
  const habEscalada: Habitacion =
    escala === 1
      ? hab
      : {
          ...hab,
          altoPared: (hab.altoPared ?? 46) * escala,
          muebles: hab.muebles.map((m) =>
            m.tipo === "sprite" ? { ...m, escala: (m.escala ?? 1) * escala } : m.tipo === "cubo" ? { ...m, alto: m.alto * escala, base: (m.base ?? 0) * escala } : m,
          ),
        };

  dibujarHabitacion(g, cam, habEscalada);
  return g;
};

const Pixeles: React.FC<{ g: Rejilla }> = ({ g }) => {
  const franjas = React.useMemo(() => aFranjas(g), [g]);
  return (
    <svg
      viewBox={`0 0 ${LOGICO_W} ${LOGICO_H}`}
      width="100%"
      height="100%"
      shapeRendering="crispEdges"
      style={{ display: "block", imageRendering: "pixelated" }}
    >
      {franjas.map((f, k) => (
        <rect key={k} x={f.x} y={f.y} width={f.w} height={1} fill={f.color} />
      ))}
    </svg>
  );
};

// ---------------------------------------------------------------- composición

const SUBTITULO: Record<Vista, { texto: string; resaltada: number }> = {
  taller: { texto: "El patronista no se equivocó.", resaltada: 3 },
  cerca: { texto: "Le mandaste un audio.", resaltada: 2 },
  parque: { texto: "Y así llevas tres colecciones.", resaltada: 1 },
};

export const PruebaPixel: React.FC<{ vista?: Vista; capitulo?: number }> = ({ vista = "taller", capitulo = 7 }) => {
  const g = React.useMemo(() => construir(vista), [vista]);
  const sub = SUBTITULO[vista];
  const palabras = sub.texto.split(" ");

  return (
    <AbsoluteFill style={{ backgroundColor: FONDO, fontFamily: FUENTE }}>
      <AbsoluteFill style={{ background: `radial-gradient(120% 70% at 50% 42%, #241c28 0%, ${FONDO} 72%)` }} />
      <AbsoluteFill>
        <Pixeles g={g} />
      </AbsoluteFill>

      {/* rótulo de episodio: es lo que convierte un reel suelto en un capítulo */}
      <div style={{ position: "absolute", left: 0, right: 0, top: 150, textAlign: "center" }}>
        <div style={{ fontSize: 30, fontWeight: 800, letterSpacing: "0.42em", color: "#9c8f74" }}>
          CAPÍTULO {String(capitulo).padStart(2, "0")}
        </div>
        <div style={{ marginTop: 18, fontSize: 62, fontWeight: 900, letterSpacing: "-0.02em", color: "#f3ead7" }}>
          El taller que adivina
        </div>
      </div>

      {/* subtítulo karaoke, discreto y abajo (regla 5 de §15) */}
      <div
        style={{
          position: "absolute",
          left: 70,
          right: 70,
          bottom: 300,
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          gap: "12px 14px",
        }}
      >
        {palabras.map((p, i) => (
          <span
            key={i}
            style={{
              fontSize: 54,
              fontWeight: 900,
              color: i === sub.resaltada ? "#ffffff" : "rgba(243,234,215,0.72)",
              backgroundColor: i === sub.resaltada ? "#9c1c2e" : "transparent",
              padding: i === sub.resaltada ? "2px 14px" : "2px 0",
              textShadow: "0 3px 12px rgba(0,0,0,0.85)",
            }}
          >
            {p}
          </span>
        ))}
      </div>
    </AbsoluteFill>
  );
};
