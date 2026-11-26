import React from "react";
import { spring } from "remotion";
import {
  Caja,
  Cilindro,
  Linea,
  MUNDO,
  Persona,
  Poly,
  RectX,
  RectY,
  RectZ,
  TextoPlanoY,
  iso,
  mezclar,
  tono,
} from "./base";

/**
 * Interiores de los 4 nichos. Cada uno existe en dos estados:
 *  - "caos":  el problema, contado con objetos (papeles, audios sueltos, obra a medias, bandeja reventada).
 *  - "orden": el mismo lugar resuelto (ficha en la pared, sala terminada, estudio con luz, agenda llena).
 *
 * Coordenadas locales del lote: x 0..220, y 0..200. Paredes de fondo en y=0 y x=0 (corte tipo maqueta).
 * `t` = frames desde que el lote entró a ese estado: los objetos entran escalonados con resorte.
 */

export type EstadoLote = "caos" | "orden";

export type PropsInterior = {
  estado: EstadoLote;
  t: number;
  frame: number;
  fps: number;
};

export const ANCHO_LOTE = 220;
export const FONDO_LOTE = 200;
const ALTO_PARED = 118;

/** Entrada con resorte: los objetos caen en su sitio uno tras otro. */
const Entra: React.FC<{ t: number; fps: number; orden: number; children: React.ReactNode }> = ({ t, fps, orden, children }) => {
  const inicio = orden * 2.5;
  if (t < inicio) return null;
  const k = spring({ frame: t - inicio, fps, config: { damping: 15, mass: 0.6, stiffness: 170 } });
  return (
    <g opacity={Math.min(1, k * 1.6)} transform={`translate(0 ${((1 - k) * -26).toFixed(1)})`}>
      {children}
    </g>
  );
};

// ------------------------------------------------------------------ habitación base

const Habitacion: React.FC<{
  piso: string;
  pared: string;
  tablones?: boolean;
  baldosa?: boolean;
  grietas?: boolean;
}> = ({ piso, pared, tablones = false, baldosa = false, grietas = false }) => {
  const W = ANCHO_LOTE;
  const D = FONDO_LOTE;
  const lineas: React.ReactNode[] = [];
  if (tablones) {
    for (let yy = 14; yy < D; yy += 14) {
      lineas.push(<Linea key={`t${yy}`} a={[0, yy, 0]} b={[W, yy, 0]} s={mezclar(piso, -0.16)} sw={0.9} />);
    }
    for (let yy = 0; yy < D; yy += 14) {
      const off = (yy / 14) % 2 === 0 ? 40 : 85;
      for (let xx = off; xx < W; xx += 95) {
        lineas.push(<Linea key={`c${yy}-${xx}`} a={[xx, yy, 0]} b={[xx, yy + 14, 0]} s={mezclar(piso, -0.16)} sw={0.8} />);
      }
    }
  }
  if (baldosa) {
    for (let v = 25; v < W; v += 25) lineas.push(<Linea key={`bx${v}`} a={[v, 0, 0]} b={[v, D, 0]} s={mezclar(piso, -0.08)} sw={0.8} />);
    for (let v = 25; v < D; v += 25) lineas.push(<Linea key={`by${v}`} a={[0, v, 0]} b={[W, v, 0]} s={mezclar(piso, -0.08)} sw={0.8} />);
  }
  return (
    <g>
      <Caja x={-8} y={-8} z={-12} w={W + 8} d={D + 8} h={12} c={tono(mezclar(piso, -0.05))} sw={1.2} />
      {lineas}
      {grietas ? (
        <g>
          <Linea a={[60, 120, 0]} b={[80, 135, 0]} s="#8f887c" sw={1.2} />
          <Linea a={[80, 135, 0]} b={[78, 152, 0]} s="#8f887c" sw={1.2} />
          <Linea a={[150, 60, 0]} b={[170, 72, 0]} s="#8f887c" sw={1.2} />
        </g>
      ) : null}
      <Caja x={-8} y={-8} w={W + 8} d={8} h={ALTO_PARED} c={tono(pared)} />
      <Caja x={-8} y={0} w={8} d={D} h={ALTO_PARED} c={tono(mezclar(pared, -0.03))} />
      <RectY Y={0} x0={0} x1={W} z0={0} z1={5} f={mezclar(pared, -0.18)} />
      <RectX X={0} y0={0} y1={D} z0={0} z1={5} f={mezclar(pared, -0.2)} />
    </g>
  );
};

const VentanaFondo: React.FC<{ x0: number; x1: number; z0?: number; z1?: number; cortina?: boolean; plastico?: boolean }> = ({
  x0, x1, z0 = 48, z1 = 98, cortina = false, plastico = false,
}) => (
  <g>
    <RectY Y={0.5} x0={x0 - 3} x1={x1 + 3} z0={z0 - 3} z1={z1 + 3} f="#f7f3ea" s="#8c8579" sw={1} />
    <RectY Y={0.8} x0={x0} x1={x1} z0={z0} z1={z1} f={MUNDO.vidrioLuz} />
    <Poly p={[[x0, 0.9, z0], [x0 + (x1 - x0) * 0.45, 0.9, z1], [x0 + (x1 - x0) * 0.62, 0.9, z1], [x0 + (x1 - x0) * 0.17, 0.9, z0]]} f="#ffffff" o={0.55} />
    <Linea a={[(x0 + x1) / 2, 1, z0]} b={[(x0 + x1) / 2, 1, z1]} s="#8c8579" sw={1.4} />
    <Linea a={[x0, 1, (z0 + z1) / 2]} b={[x1, 1, (z0 + z1) / 2]} s="#8c8579" sw={1.4} />
    {cortina ? (
      <>
        <RectY Y={1.4} x0={x0 - 8} x1={x0 + 6} z0={z0 - 6} z1={z1 + 8} f={MUNDO.vino} />
        <RectY Y={1.4} x0={x1 - 6} x1={x1 + 8} z0={z0 - 6} z1={z1 + 8} f={MUNDO.vino} />
      </>
    ) : null}
    {plastico ? <RectY Y={1.4} x0={x0 - 4} x1={x1 + 4} z0={z0 - 4} z1={z1 + 4} f="#e8e6e0" o={0.75} s="#b5b0a6" sw={0.8} /> : null}
  </g>
);

const Mesa: React.FC<{ x: number; y: number; w: number; d: number; h: number; color: string; z?: number }> = ({ x, y, w, d, h, color, z = 0 }) => (
  <g>
    <Caja x={x + 2} y={y + d - 5} z={z} w={3} d={3} h={h - 5} c={tono("#6b6258")} sw={0.6} />
    <Caja x={x + w - 5} y={y + d - 5} z={z} w={3} d={3} h={h - 5} c={tono("#6b6258")} sw={0.6} />
    <Caja x={x + w - 5} y={y + 2} z={z} w={3} d={3} h={h - 5} c={tono("#6b6258")} sw={0.6} />
    <Caja x={x} y={y} z={z + h - 5} w={w} d={d} h={5} c={tono(color)} />
  </g>
);

const BolaPapel: React.FC<{ x: number; y: number; z?: number }> = ({ x, y, z = 0 }) => {
  const [sx, sy] = iso(x, y, z + 3);
  return (
    <g>
      <circle cx={sx} cy={sy} r={4.2} fill="#f6f2ea" stroke="#9a9488" strokeWidth={0.9} />
      <path d={`M ${sx - 2.5} ${sy - 1} L ${sx + 1} ${sy + 1.5} M ${sx - 0.5} ${sy - 2.5} L ${sx + 2} ${sy}`} stroke="#9a9488" strokeWidth={0.7} />
    </g>
  );
};

const CajaCarton: React.FC<{ x: number; y: number; z?: number; w?: number; d?: number; h?: number; rotulo?: string }> = ({
  x, y, z = 0, w = 26, d = 22, h = 20, rotulo,
}) => (
  <g>
    <Caja x={x} y={y} z={z} w={w} d={d} h={h} c={tono("#c9a77c")} />
    <Linea a={[x + w / 2, y, z + h]} b={[x + w / 2, y + d, z + h]} s="#9b7c52" sw={1} />
    {rotulo ? <TextoPlanoY x={x + w / 2} Y={y + d + 0.4} z={z + h / 2} texto={rotulo} size={5.5} color={MUNDO.vino} peso={900} espaciado={0.4} /> : null}
  </g>
);

// ------------------------------------------------------------------ TALLER DE CONFECCIÓN

const Prenda: React.FC<{ x: number; y: number; z: number; color: string; torcida?: number }> = ({ x, y, z, color, torcida = 0 }) => (
  <g>
    <Linea a={[x + 4, y, z + 34]} b={[x + 4, y, z + 38]} s="#5c5c5c" sw={1.2} />
    <Poly
      p={[
        [x - 2 + torcida, y - 6, z + 33],
        [x + 10 + torcida, y - 6, z + 33],
        [x + 12, y - 6, z + 2],
        [x - 4, y - 6, z + 2],
      ]}
      f={color}
      s={mezclar(color, -0.4)}
      sw={0.9}
    />
    <Poly
      p={[
        [x - 4, y - 6, z + 2],
        [x + 12, y - 6, z + 2],
        [x + 12, y + 6, z + 2],
        [x - 4, y + 6, z + 2],
      ]}
      f={mezclar(color, -0.15)}
      s={mezclar(color, -0.4)}
      sw={0.6}
    />
  </g>
);

const MaquinaCoser: React.FC<{ x: number; y: number; z: number; frame: number }> = ({ x, y, z, frame }) => {
  const aguja = Math.abs(Math.sin(frame * 0.9)) * 3;
  return (
    <g>
      <Caja x={x} y={y} z={z} w={22} d={11} h={4} c={tono("#f1ede4")} />
      <Caja x={x + 15} y={y + 2} z={z + 4} w={6} d={7} h={14} c={tono("#f1ede4")} />
      <Caja x={x + 1} y={y + 2} z={z + 14} w={20} d={7} h={5} c={tono("#f1ede4")} />
      <Caja x={x + 1} y={y + 3} z={z + 4 + aguja} w={3} d={3} h={10 - aguja} c={tono("#cfcac0")} sw={0.6} />
      <RectY Y={y + 9.2} x0={x + 6} x1={x + 14} z0={z + 15} z1={z + 18} f={MUNDO.vino} />
    </g>
  );
};

export const InteriorTaller: React.FC<PropsInterior> = ({ estado, t, frame, fps }) => {
  const caos = estado === "caos";
  return (
    <g>
      <Habitacion piso="#d9cfbd" pared="#ece4d4" baldosa />
      {/* Pared de fondo: ventana + tablero (la ficha vive aquí) */}
      <VentanaFondo x0={150} x1={205} />
      <RectY Y={0.6} x0={22} x1={122} z0={52} z1={108} f="#c49b70" s="#8a6a48" sw={1.2} />
      {caos ? (
        <Entra t={t} fps={fps} orden={0}>
          {[
            [30, 95, "#f2d36b"], [52, 70, "#f3a9a0"], [78, 98, "#f2d36b"], [96, 66, "#c9dbb2"], [104, 90, "#f3a9a0"], [40, 62, "#f2d36b"],
          ].map(([xx, zz, c], i) => (
            <RectY key={i} Y={1} x0={Number(xx)} x1={Number(xx) + 13} z0={Number(zz)} z1={Number(zz) + 11} f={String(c)} s="#a08a5c" sw={0.5} />
          ))}
          <TextoPlanoY x={72} Y={1.2} z={83} texto="?" size={30} color={MUNDO.vino} peso={900} />
        </Entra>
      ) : (
        <Entra t={t} fps={fps} orden={0}>
          <RectY Y={1} x0={30} x1={86} z0={57} z1={104} f="#ffffff" s="#8a8478" sw={0.8} />
          <TextoPlanoY x={58} Y={1.2} z={99} texto="FICHA TÉCNICA" size={4.6} color={MUNDO.tinta} peso={900} espaciado={0.3} />
          {/* Camiseta plana con cotas */}
          <Poly
            p={[
              [42, 1.3, 92], [50, 1.3, 94], [66, 1.3, 94], [74, 1.3, 92], [79, 1.3, 85], [72, 1.3, 82], [70, 1.3, 85], [70, 1.3, 64], [46, 1.3, 64], [46, 1.3, 85], [44, 1.3, 82], [37, 1.3, 85],
            ]}
            f="#f3ece0"
            s={MUNDO.tinta}
            sw={0.9}
          />
          <Linea a={[46, 1.4, 61]} b={[70, 1.4, 61]} s={MUNDO.vino} sw={1} />
          <Linea a={[73, 1.4, 64]} b={[73, 1.4, 80]} s={MUNDO.vino} sw={1} />
          <Linea a={[50, 1.4, 96.5]} b={[66, 1.4, 96.5]} s={MUNDO.vino} sw={1} />
          <RectY Y={1} x0={90} x1={116} z0={60} z1={104} f="#ffffff" s="#8a8478" sw={0.8} />
          {[96, 90, 84, 78, 72, 66].map((zz) => (
            <Linea key={zz} a={[93, 1.3, zz]} b={[zz % 12 === 0 ? 108 : 113, 1.3, zz]} s="#9a948a" sw={1.1} />
          ))}
          <circle cx={iso(112, 1.4, 100)[0]} cy={iso(112, 1.4, 100)[1]} r={3} fill={MUNDO.vino} />
        </Entra>
      )}
      {/* Pared lateral: estante de hilos */}
      <Caja x={0} y={30} z={70} w={14} d={120} h={4} c={tono("#a98c6c")} />
      {[40, 55, 70, 85, 100, 115, 130].map((yy, i) => (
        <Cilindro key={yy} x={7} y={yy} z={74} r={4} h={10} c={tono(["#9c1c2e", "#d9a441", "#5f7a5c", "#3f5163", "#e9e2d3", "#6c5a7d", "#c58c63"][i])} />
      ))}
      <Caja x={0} y={30} z={42} w={14} d={120} h={4} c={tono("#a98c6c")} />
      {[38, 62, 86, 110, 134].map((yy, i) => (
        <Caja key={yy} x={2} y={yy} z={46} w={10} d={18} h={10} c={tono(["#8a3d4a", "#d9c7a8", "#5f7a5c", "#c9a77c", "#3f5163"][i])} sw={0.7} />
      ))}
      {/* Perchero */}
      <Linea a={[150, 22, 0]} b={[150, 22, 72]} s="#5c5c5c" sw={2} />
      <Linea a={[208, 22, 0]} b={[208, 22, 72]} s="#5c5c5c" sw={2} />
      <Linea a={[150, 22, 72]} b={[208, 22, 72]} s="#5c5c5c" sw={2.2} />
      {caos
        ? [[156, "#9c1c2e", 4], [176, "#d9a441", -5], [196, "#5f7a5c", 7]].map(([xx, c, tw]) => (
            <Prenda key={String(xx)} x={Number(xx)} y={22} z={34} color={String(c)} torcida={Number(tw)} />
          ))
        : [156, 167, 178, 189, 200].map((xx, i) => (
            <Entra key={xx} t={t} fps={fps} orden={1 + i * 0.6}>
              <Prenda x={xx} y={22} z={34} color={i % 2 === 0 ? "#e9e2d3" : "#d7ccb8"} />
            </Entra>
          ))}
      {caos ? <Poly p={[[160, 40, 0.5], [190, 36, 0.5], [196, 52, 0.5], [164, 56, 0.5]]} f={MUNDO.vino} s={MUNDO.vinoOscuro} sw={0.8} /> : null}
      {/* Mesa de corte */}
      <Mesa x={40} y={48} w={110} d={44} h={40} color="#d8c3a0" />
      <RectZ z={40.5} x0={50} y0={54} x1={126} y1={86} f={caos ? "#8a3d4a" : "#7a2f3d"} s={MUNDO.vinoOscuro} sw={0.8} />
      {caos ? (
        <Entra t={t} fps={fps} orden={1}>
          <BolaPapel x={60} y={64} z={41} />
          <BolaPapel x={118} y={58} z={41} />
          <BolaPapel x={100} y={80} z={41} />
          {/* Celular con audios sueltos */}
          <Caja x={130} y={60} z={40} w={12} d={18} h={2} c={tono("#2f2f35")} sw={0.6} />
          {[0, 1, 2].map((i) => {
            const [bx, by] = iso(136, 69, 52 + i * 15);
            const vib = Math.sin(frame * 0.35 + i) * 1.5;
            return (
              <g key={i} transform={`translate(${bx + 14 + vib} ${by - i * 2})`}>
                <rect x={0} y={-8} width={40} height={16} rx={8} fill="#ffffff" stroke="#9a948a" strokeWidth={0.8} />
                <circle cx={8} cy={0} r={3.2} fill={MUNDO.vino} />
                {[14, 18, 22, 26, 30, 34].map((wx, k) => (
                  <line key={wx} x1={wx} x2={wx} y1={-2 - ((k * 7 + i) % 4)} y2={2 + ((k * 7 + i) % 4)} stroke="#6e6e73" strokeWidth={1.4} />
                ))}
              </g>
            );
          })}
        </Entra>
      ) : (
        <Entra t={t} fps={fps} orden={2}>
          <Poly p={[[58, 58, 41], [84, 58, 41], [88, 76, 41], [60, 80, 41]]} f="#f3ece0" s="#8a8478" sw={0.8} />
          <Poly p={[[94, 60, 41], [116, 60, 41], [116, 82, 41], [94, 82, 41]]} f="#f3ece0" s="#8a8478" sw={0.8} />
          <Linea a={[56, 88, 41]} b={[124, 88, 41]} s="#d9a441" sw={2.6} />
          <Caja x={128} y={60} z={40} w={14} d={20} h={1.5} c={tono("#ffffff")} sw={0.6} />
        </Entra>
      )}
      {/* Patronista */}
      <Persona x={95} y={104} semilla={3} ropa={caos ? "#3f5163" : "#2f2f35"} cabizbaja={caos} />
      {/* Estaciones de costura */}
      <Mesa x={14} y={124} w={52} d={24} h={30} color="#cdb894" />
      <MaquinaCoser x={30} y={129} z={30} frame={frame} />
      <Persona x={40} y={162} semilla={5} sentada />
      <Mesa x={82} y={124} w={52} d={24} h={30} color="#cdb894" />
      <MaquinaCoser x={98} y={129} z={30} frame={frame + 3} />
      <Persona x={108} y={162} semilla={8} sentada ropa="#6c5a7d" />
      {/* Maniquí */}
      <ellipse cx={iso(182, 150, 0)[0]} cy={iso(182, 150, 0)[1]} rx={13} ry={6} fill="#6b6258" />
      <Linea a={[182, 150, 0]} b={[182, 150, 40]} s="#6b6258" sw={2.4} />
      <Caja x={174} y={144} z={40} w={16} d={12} h={30} c={tono(caos ? MUNDO.vino : "#efe8da")} />
      <Caja x={178} y={147} z={70} w={8} d={6} h={6} c={tono("#d7cdbd")} />
      {caos ? (
        <Poly p={[[174, 156, 40], [190, 156, 46], [190, 156, 40]]} f={MUNDO.vinoOscuro} />
      ) : (
        <RectY Y={156.3} x0={174} x1={190} z0={58} z1={60} f={MUNDO.vino} />
      )}
      {/* Cajas del lote */}
      {caos ? (
        <Entra t={t} fps={fps} orden={2}>
          <CajaCarton x={170} y={170} rotulo="DEVUELTO" />
          <CajaCarton x={188} y={176} z={0} w={22} d={18} h={16} />
          <BolaPapel x={150} y={182} />
          <BolaPapel x={70} y={186} />
          <Poly p={[[120, 176, 0.5], [138, 172, 0.5], [142, 186, 0.5], [124, 190, 0.5]]} f="#d9a441" o={0.9} />
        </Entra>
      ) : (
        <Entra t={t} fps={fps} orden={3}>
          <CajaCarton x={166} y={168} rotulo="LISTO" />
          <CajaCarton x={166} y={168} z={20} rotulo="LISTO" />
          <CajaCarton x={192} y={172} w={20} d={20} h={18} rotulo="LISTO" />
        </Entra>
      )}
    </g>
  );
};

// ------------------------------------------------------------------ OBRA / REMODELACIÓN

const Planta: React.FC<{ x: number; y: number; z?: number; alto?: number }> = ({ x, y, z = 0, alto = 30 }) => {
  const [cx, cy] = iso(x, y, z + 12 + alto * 0.55);
  return (
    <g>
      <Cilindro x={x} y={y} z={z} r={7} h={12} c={tono("#b9876a")} />
      <circle cx={cx} cy={cy} r={alto * 0.42} fill="#6f8a5e" stroke="#4f6542" strokeWidth={1} />
      <circle cx={cx - 6} cy={cy - 7} r={alto * 0.25} fill="#89a173" />
      <circle cx={cx + 7} cy={cy - 3} r={alto * 0.22} fill="#7c9667" />
    </g>
  );
};

export const InteriorObra: React.FC<PropsInterior> = ({ estado, t, frame, fps }) => {
  if (estado === "caos") {
    const polvo = (frame * 0.4) % 30;
    return (
      <g>
        <Habitacion piso="#b1a998" pared="#d3cbbb" grietas />
        {/* Ladrillo expuesto */}
        {Array.from({ length: 6 }).map((_, f) =>
          Array.from({ length: 5 }).map((__, c) => (
            <RectY key={`${f}-${c}`} Y={0.6} x0={20 + c * 13 + (f % 2) * 6} x1={31 + c * 13 + (f % 2) * 6} z0={40 + f * 7} z1={45.5 + f * 7} f="#b5765a" s="#8a5640" sw={0.5} />
          )),
        )}
        <VentanaFondo x0={130} x1={190} plastico />
        {/* Cables colgando + caja eléctrica abierta */}
        <RectX X={0.6} y0={60} y1={80} z0={70} z1={90} f="#9a948a" s="#5c5c5c" sw={0.8} />
        <Linea a={[0.8, 66, 70]} b={[0.8, 64, 40]} s="#2f2f35" sw={1.6} />
        <Linea a={[0.8, 74, 70]} b={[0.8, 80, 48]} s={MUNDO.vino} sw={1.6} />
        {/* Andamio */}
        <Entra t={t} fps={fps} orden={0}>
          {[[120, 14], [190, 14], [120, 44], [190, 44]].map(([xx, yy]) => (
            <Linea key={`${xx}-${yy}`} a={[xx, yy, 0]} b={[xx, yy, 78]} s="#6d6a64" sw={2} />
          ))}
          <Caja x={118} y={12} z={40} w={74} d={34} h={4} c={tono("#b08a5a")} />
          <Caja x={118} y={12} z={78} w={74} d={34} h={4} c={tono("#b08a5a")} />
          <Linea a={[120, 44, 0]} b={[190, 44, 40]} s="#6d6a64" sw={1.4} />
          <Persona x={160} y={28} z={44} semilla={6} casco ropa="#5f7a5c" brazosArriba />
        </Entra>
        {/* Escalera */}
        <Linea a={[6, 150, 0]} b={[1, 140, 92]} s="#8a7a62" sw={2.2} />
        <Linea a={[6, 170, 0]} b={[1, 160, 92]} s="#8a7a62" sw={2.2} />
        {[15, 30, 45, 60, 75].map((zz) => (
          <Linea key={zz} a={[5.2, 148.4, zz]} b={[5.2, 168.4, zz]} s="#8a7a62" sw={1.6} />
        ))}
        {/* Mesa de planos (caballetes) */}
        <Entra t={t} fps={fps} orden={1}>
          <Mesa x={36} y={118} w={62} d={32} h={34} color="#c8b08a" />
          <RectZ z={34.6} x0={40} y0={121} x1={94} y1={147} f="#3f5f80" s="#2c4560" sw={0.8} />
          {[126, 132, 138].map((yy) => (
            <Linea key={yy} a={[44, yy, 34.8]} b={[88, yy, 34.8]} s="#c9d6e2" sw={0.8} />
          ))}
          <Linea a={[66, 122, 34.8]} b={[66, 146, 34.8]} s="#c9d6e2" sw={0.8} />
          <Cilindro x={96} y={144} z={34} r={2.5} h={2} c={tono("#d8d0c0")} />
          <Persona x={70} y={162} semilla={2} casco ropa="#3f5163" />
        </Entra>
        {/* Baldes, sacos, polvo */}
        <Entra t={t} fps={fps} orden={2}>
          <Cilindro x={130} y={110} r={8} h={14} c={tono("#e9e2d3")} />
          <Cilindro x={148} y={118} r={8} h={14} c={tono("#e9e2d3")} />
          <RectZ z={14.2} x0={124} y0={106} x1={136} y1={114} f="#d9a441" o={0.8} />
          <Caja x={170} y={150} w={26} d={18} h={8} c={tono("#d8d0bf")} />
          <Caja x={172} y={152} z={8} w={24} d={16} h={8} c={tono("#d0c8b6")} />
          <Caja x={110} y={170} w={40} d={6} h={4} c={tono("#b08a5a")} />
          <Caja x={116} y={164} z={4} w={40} d={6} h={4} c={tono("#a8814f")} />
          {[0, 1, 2, 3].map((i) => {
            const [px, py] = iso(60 + i * 35, 80 + ((i * 37) % 60), 10 + ((polvo + i * 8) % 30));
            return <circle key={i} cx={px} cy={py} r={5 + i} fill="#ffffff" opacity={0.25} />;
          })}
        </Entra>
        {/* Escombro de la pared rota, carretilla, herramientas y segundo maestro */}
        <Entra t={t} fps={fps} orden={3}>
          {[[28, 18, 9, "#b5765a"], [40, 24, 7, "#a9674c"], [22, 32, 6, "#b9b2a5"], [48, 14, 6, "#b5765a"], [34, 36, 8, "#9f9a8f"], [56, 28, 5, "#b5765a"]].map(([xx, yy, hh, c], i) => (
            <Caja key={i} x={Number(xx)} y={Number(yy)} w={10 + (i % 3) * 3} d={8 + (i % 2) * 4} h={Number(hh)} c={tono(String(c))} sw={0.7} />
          ))}
          {/* Carretilla */}
          <Caja x={84} y={60} z={8} w={30} d={20} h={12} c={tono("#7a8590")} />
          <RectZ z={20.2} x0={86} y0={62} x1={112} y1={78} f="#9f9a8f" />
          <Linea a={[114, 64, 12]} b={[130, 60, 16]} s="#5c5c5c" sw={2} />
          <Linea a={[114, 76, 12]} b={[130, 74, 16]} s="#5c5c5c" sw={2} />
          <circle cx={iso(84, 70, 6)[0]} cy={iso(84, 70, 6)[1]} r={6} fill="#2d2d2d" />
          {/* Caballete con tablas */}
          <Mesa x={140} y={84} w={50} d={14} h={22} color="#b08a5a" />
          <Caja x={136} y={86} z={22} w={58} d={4} h={3} c={tono("#c9a06a")} />
          <Caja x={136} y={92} z={22} w={58} d={4} h={3} c={tono("#c9a06a")} />
          {/* Caja de herramientas + taladro */}
          <Caja x={150} y={128} w={22} d={12} h={10} c={tono(MUNDO.vino)} />
          <Caja x={156} y={126} z={10} w={10} d={4} h={4} c={tono("#3d3a35")} sw={0.6} />
          {/* Baldosas apiladas */}
          {[0, 1, 2, 3, 4].map((k) => (
            <Caja key={k} x={192} y={112} z={k * 3} w={18} d={18} h={3} c={tono(k % 2 ? "#e4dacb" : "#d8cdbb")} sw={0.6} />
          ))}
          {/* Cable de extensión en el piso */}
          <path
            d={`M ${iso(2, 78, 0)[0]} ${iso(2, 78, 0)[1]} Q ${iso(60, 100, 0)[0]} ${iso(60, 100, 0)[1]} ${iso(100, 110, 0)[0]} ${iso(100, 110, 0)[1]} T ${iso(150, 132, 0)[0]} ${iso(150, 132, 0)[1]}`}
            stroke="#2f2f35"
            strokeWidth={2}
            fill="none"
          />
          <Persona x={120} y={112} semilla={11} casco ropa="#3f5163" />
          <Caja x={112} y={186} w={34} d={8} h={6} c={tono("#9f9a8f")} />
          <Cilindro x={196} y={186} r={7} h={12} c={tono("#e9e2d3")} />
          <Cilindro x={60} y={186} r={6} h={10} c={tono(MUNDO.vino)} />
        </Entra>
      </g>
    );
  }
  return (
    <g>
      <Habitacion piso={MUNDO.madera} pared="#efe7d8" tablones />
      <RectY Y={0.5} x0={0} x1={220} z0={0} z1={30} f="#e4dac6" />
      <Linea a={[0, 0.7, 30]} b={[220, 0.7, 30]} s="#c9bea8" sw={1.4} />
      <VentanaFondo x0={140} x1={200} z0={44} z1={100} cortina />
      {/* Cuadros */}
      <Entra t={t} fps={fps} orden={0}>
        <RectY Y={0.8} x0={30} x1={70} z0={58} z1={92} f="#ffffff" s="#3d3a35" sw={1.6} />
        <Poly p={[[34, 1, 62], [52, 1, 80], [66, 1, 62]]} f={MUNDO.vino} />
        <circle cx={iso(58, 1, 84)[0]} cy={iso(58, 1, 84)[1]} r={4} fill="#d9a441" />
        <RectY Y={0.8} x0={80} x1={108} z0={64} z1={92} f="#ffffff" s="#3d3a35" sw={1.6} />
        <RectY Y={1} x0={84} x1={104} z0={68} z1={88} f="#9aa58c" />
      </Entra>
      {/* Mueble TV en pared lateral */}
      <Entra t={t} fps={fps} orden={1}>
        <Caja x={0} y={70} w={16} d={84} h={22} c={tono("#8c6a4a")} />
        <RectX X={0.8} y0={78} y1={146} z0={40} z1={82} f="#1f1f24" s="#0a0a0a" sw={1.2} />
        <Poly p={[[1, 84, 46], [1, 100, 76], [1, 108, 76], [1, 92, 46]]} f="#ffffff" o={0.12} />
        <Planta x={10} y={168} alto={34} />
      </Entra>
      {/* Alfombra + sofá + mesa */}
      <Entra t={t} fps={fps} orden={2}>
        <RectZ z={0.6} x0={46} y0={64} x1={176} y1={170} f="#efe5d2" s={MUNDO.vino} sw={3} />
        <Caja x={50} y={22} w={120} d={36} h={16} c={tono("#6f7f8f")} />
        <Caja x={50} y={18} w={120} d={10} h={36} c={tono("#64737f")} />
        <Caja x={44} y={18} w={8} d={40} h={24} c={tono("#64737f")} />
        <Caja x={168} y={18} w={8} d={40} h={24} c={tono("#64737f")} />
        {[56, 92, 128].map((xx) => (
          <Caja key={xx} x={xx} y={26} z={16} w={34} d={28} h={5} c={tono("#7b8c9c")} sw={0.8} />
        ))}
        <Caja x={150} y={28} z={21} w={12} d={8} h={12} c={tono(MUNDO.vino)} sw={0.8} />
      </Entra>
      <Entra t={t} fps={fps} orden={3}>
        <Caja x={86} y={92} w={54} d={34} h={4} c={tono("#3d3a35")} z={18} />
        <Linea a={[90, 124, 0]} b={[90, 124, 18]} s="#3d3a35" sw={2} />
        <Linea a={[136, 124, 0]} b={[136, 124, 18]} s="#3d3a35" sw={2} />
        <Linea a={[136, 94, 0]} b={[136, 94, 18]} s="#3d3a35" sw={2} />
        <Cilindro x={104} y={104} z={22} r={4} h={6} c={tono("#ffffff")} />
        <Caja x={116} y={100} z={22} w={14} d={10} h={3} c={tono("#d9a441")} sw={0.6} />
        {/* Sillón */}
        <Caja x={180} y={96} w={30} d={36} h={16} c={tono("#c9935f")} />
        <Caja x={180} y={96} w={30} d={8} h={32} c={tono("#b8834f")} />
        {/* Lámpara de pie */}
        <Linea a={[196, 72, 0]} b={[196, 72, 74]} s="#3d3a35" sw={1.8} />
        <Cilindro x={196} y={72} z={70} r={9} h={12} c={tono("#f3e7c6")} />
        <circle cx={iso(196, 72, 64)[0]} cy={iso(196, 72, 64)[1]} r={26} fill="#fff4d6" opacity={0.25} />
        <Planta x={40} y={180} alto={40} />
        <Persona x={130} y={150} semilla={4} ropa={MUNDO.vino} />
      </Entra>
    </g>
  );
};

// ------------------------------------------------------------------ ESTUDIO DE CATÁLOGO

const Softbox: React.FC<{ x: number; y: number; encendida: boolean; frame: number }> = ({ x, y, encendida, frame }) => {
  const [gx, gy] = iso(x + 4, y + 12, 78);
  const pulso = 0.32 + Math.sin(frame * 0.15) * 0.04;
  return (
    <g>
      <Linea a={[x + 3, y + 12, 0]} b={[x + 3, y + 12, 70]} s="#2f2f35" sw={2} />
      <Linea a={[x + 3, y + 12, 0]} b={[x - 8, y + 4, 0]} s="#2f2f35" sw={1.6} />
      <Linea a={[x + 3, y + 12, 0]} b={[x + 12, y + 22, 0]} s="#2f2f35" sw={1.6} />
      {encendida ? <circle cx={gx} cy={gy} r={46} fill="#fffaf0" opacity={pulso} /> : null}
      <Caja x={x} y={y} z={66} w={8} d={26} h={26} c={encendida ? tono("#fffdf6", "#8a8478") : tono("#5a5a60")} />
    </g>
  );
};

export const InteriorEstudio: React.FC<PropsInterior> = ({ estado, t, frame, fps }) => {
  const caos = estado === "caos";
  const flash = caos && frame % 40 < 4;
  return (
    <g>
      <Habitacion piso={caos ? "#cfc7b8" : "#e9e5dc"} pared={caos ? "#ddd4c3" : "#f1ede4"} baldosa={caos} />
      {caos ? (
        <g>
          <VentanaFondo x0={30} x1={80} />
          {/* Inventario apilado esperando foto */}
          <Entra t={t} fps={fps} orden={0}>
            <CajaCarton x={120} y={10} w={30} d={26} h={22} rotulo="SIN FOTO" />
            <CajaCarton x={150} y={10} w={30} d={26} h={22} />
            <CajaCarton x={180} y={10} w={30} d={26} h={22} rotulo="SIN FOTO" />
            <CajaCarton x={125} y={12} z={22} w={30} d={24} h={20} />
            <CajaCarton x={158} y={12} z={22} w={30} d={24} h={20} rotulo="SIN FOTO" />
            <CajaCarton x={140} y={14} z={42} w={28} d={22} h={18} />
            <CajaCarton x={170} y={44} w={30} d={26} h={22} />
            <CajaCarton x={186} y={74} w={24} d={24} h={18} rotulo="SIN FOTO" />
          </Entra>
          {/* Mesa con producto y foto con celular */}
          <Entra t={t} fps={fps} orden={1}>
            <Mesa x={50} y={80} w={70} d={40} h={34} color="#bfae92" />
            <Caja x={74} y={92} z={34} w={18} d={10} h={14} c={tono(MUNDO.vino)} />
            <Poly p={[[100, 96, 34.5], [116, 92, 34.5], [118, 110, 34.5], [104, 114, 34.5]]} f="#6c5a7d" o={0.9} />
            <BolaPapel x={60} y={110} z={34} />
            <Persona x={96} y={150} semilla={7} ropa="#d9a441" brazosArriba />
            {flash ? <circle cx={iso(96, 150, 66)[0]} cy={iso(96, 150, 66)[1]} r={38} fill="#ffffff" opacity={0.85} /> : null}
          </Entra>
          {/* Ropa amontonada */}
          <Entra t={t} fps={fps} orden={2}>
            {[[30, 160, "#3f5163"], [40, 172, "#e9e2d3"], [22, 176, MUNDO.vino], [48, 184, "#5f7a5c"]].map(([xx, yy, c], i) => {
              const [sx, sy] = iso(Number(xx), Number(yy), 4);
              return <ellipse key={i} cx={sx} cy={sy} rx={18} ry={8} fill={String(c)} stroke="#2f2f35" strokeWidth={0.6} />;
            })}
          </Entra>
        </g>
      ) : (
        <g>
          {/* Fondo infinito blanco */}
          <RectY Y={0.6} x0={46} x1={176} z0={0} z1={108} f="#ffffff" />
          <RectZ z={0.4} x0={46} y0={0} x1={176} y1={86} f="#ffffff" />
          <Entra t={t} fps={fps} orden={0}>
            <Softbox x={20} y={30} encendida frame={frame} />
            <Softbox x={190} y={60} encendida frame={frame + 9} />
          </Entra>
          <Entra t={t} fps={fps} orden={1}>
            <Caja x={96} y={30} w={30} d={30} h={26} c={tono("#f4f1ea", "#a8a296")} />
            <Caja x={102} y={38} z={26} w={18} d={12} h={18} c={tono(MUNDO.vino)} />
            <path
              d={`M ${iso(105, 44, 44)[0]} ${iso(105, 44, 44)[1]} Q ${iso(111, 44, 54)[0]} ${iso(111, 44, 54)[1]} ${iso(117, 44, 44)[0]} ${iso(117, 44, 44)[1]}`}
              stroke={MUNDO.vinoOscuro}
              strokeWidth={2}
              fill="none"
            />
            <Poly p={[[102, 50, 30], [104, 50, 42], [107, 50, 42], [105, 50, 30]]} f="#ffffff" o={0.5} />
          </Entra>
          {/* Cámara en trípode + fotógrafo */}
          <Entra t={t} fps={fps} orden={2}>
            <Linea a={[112, 132, 44]} b={[100, 124, 0]} s="#2f2f35" sw={1.8} />
            <Linea a={[112, 132, 44]} b={[124, 128, 0]} s="#2f2f35" sw={1.8} />
            <Linea a={[112, 132, 44]} b={[112, 146, 0]} s="#2f2f35" sw={1.8} />
            <Caja x={104} y={126} z={44} w={16} d={10} h={11} c={tono("#2f2f35")} />
            <Cilindro x={112} y={124} z={46} r={4} h={4} c={tono("#1c1c20")} />
            <Persona x={118} y={160} semilla={1} ropa="#2f2f35" />
          </Entra>
          {/* Perchero con lo ya fotografiado + cajas listas para despacho */}
          <Entra t={t} fps={fps} orden={2.5}>
            <Linea a={[150, 150, 0]} b={[150, 150, 66]} s="#5c5c5c" sw={2} />
            <Linea a={[150, 196, 0]} b={[150, 196, 66]} s="#5c5c5c" sw={2} />
            <Linea a={[150, 150, 66]} b={[150, 196, 66]} s="#5c5c5c" sw={2.2} />
            {[156, 166, 176, 186].map((yy, i) => (
              <Caja key={yy} x={146} y={yy - 3} z={30} w={8} d={6} h={33} c={tono([MUNDO.vino, "#d9a441", "#6c5a7d", "#3f5163"][i])} sw={0.6} />
            ))}
            <CajaCarton x={176} y={176} w={22} d={20} h={16} rotulo="LISTO" />
            <CajaCarton x={198} y={150} w={18} d={18} h={14} rotulo="LISTO" />
            <Persona x={70} y={60} semilla={12} ropa="#e9e2d3" />
          </Entra>
          {/* Laptop con el catálogo armado */}
          <Entra t={t} fps={fps} orden={3}>
            <Mesa x={8} y={118} w={40} d={56} h={32} color="#d8cdb9" />
            <Caja x={18} y={128} z={32} w={20} d={32} h={1.5} c={tono("#d8d8d8")} sw={0.6} />
            <RectX X={18.5} y0={128} y1={160} z0={33} z1={56} f="#ffffff" s="#5c5c5c" sw={1} />
            {[0, 1, 2].map((c) =>
              [0, 1].map((r) => (
                <RectX key={`${c}-${r}`} X={19} y0={131 + c * 9.5} y1={138.5 + c * 9.5} z0={37 + r * 9} z1={44 + r * 9} f={[MUNDO.vino, "#d9a441", "#6c5a7d"][(c + r) % 3]} />
              )),
            )}
          </Entra>
        </g>
      )}
    </g>
  );
};

// ------------------------------------------------------------------ OFICINA / AGENCIA

const Sobre: React.FC<{ sx: number; sy: number; escala?: number }> = ({ sx, sy, escala = 1 }) => (
  <g transform={`translate(${sx} ${sy}) scale(${escala})`}>
    <rect x={-9} y={-6} width={18} height={12} rx={1.5} fill="#ffffff" stroke={MUNDO.vino} strokeWidth={1.2} />
    <path d="M -9 -6 L 0 1 L 9 -6" stroke={MUNDO.vino} strokeWidth={1.2} fill="none" />
  </g>
);

export const InteriorOficina: React.FC<PropsInterior> = ({ estado, t, frame, fps }) => {
  const caos = estado === "caos";
  return (
    <g>
      <Habitacion piso="#cbc6bc" pared="#eee8dc" baldosa />
      <VentanaFondo x0={150} x1={205} />
      {/* Tablero / agenda en la pared */}
      <RectY Y={0.6} x0={24} x1={126} z0={50} z1={106} f="#ffffff" s="#5c5c5c" sw={1.4} />
      <TextoPlanoY x={75} Y={0.9} z={101} texto="AGENDA" size={5.5} color={MUNDO.tinta} peso={900} espaciado={0.6} />
      {[0, 1, 2, 3, 4].map((c) => (
        <Linea key={c} a={[30 + c * 19, 1, 54]} b={[30 + c * 19, 1, 96]} s="#d6d0c4" sw={0.8} />
      ))}
      {[62, 72, 82].map((zz) => (
        <Linea key={zz} a={[28, 1, zz]} b={[122, 1, zz]} s="#d6d0c4" sw={0.8} />
      ))}
      {caos ? (
        <g>
          {[[34, 86, "#f2d36b"], [70, 64, "#f3a9a0"], [98, 78, "#f2d36b"]].map(([xx, zz, c], i) => (
            <RectY key={i} Y={1.1} x0={Number(xx)} x1={Number(xx) + 12} z0={Number(zz)} z1={Number(zz) + 10} f={String(c)} />
          ))}
        </g>
      ) : (
        <Entra t={t} fps={fps} orden={0}>
          {[[31, 83, 46], [50, 73, 65], [69, 85, 84], [88, 63, 103], [107, 75, 122]].map(([x0, z0, x1], i) => (
            <RectY key={i} Y={1.1} x0={x0} x1={Math.min(Number(x1), x0 + 16)} z0={z0} z1={Number(z0) + 8} f={MUNDO.vino} />
          ))}
        </Entra>
      )}
      {/* Estantería lateral */}
      <Caja x={0} y={20} w={18} d={70} h={88} c={tono("#a98c6c")} />
      {[30, 50, 70].map((zz) =>
        [26, 36, 46, 56, 66, 76].map((yy, i) => (
          <RectX key={`${zz}-${yy}`} X={18.3} y0={yy} y1={yy + 8} z0={zz} z1={zz + 14} f={["#3f5163", MUNDO.vino, "#d9a441", "#5f7a5c", "#e9e2d3", "#6c5a7d"][(i + zz) % 6]} />
        )),
      )}
      {/* Escritorio principal */}
      <Mesa x={60} y={82} w={112} d={40} h={32} color="#d8c3a0" />
      <Caja x={108} y={92} z={32} w={14} d={8} h={8} c={tono("#3d3a35")} />
      <Caja x={86} y={92} z={40} w={60} d={4} h={34} c={tono("#2f2f35")} />
      <RectY Y={96.3} x0={89} x1={143} z0={43} z1={71} f={caos ? "#1c1c20" : "#ffffff"} />
      {caos ? (
        <g>
          {[[96, 66], [110, 60], [124, 66], [104, 52], [130, 52], [118, 48]].map(([xx, zz], i) => {
            const [sx, sy] = iso(xx, 96.6, zz);
            const late = 1 + Math.max(0, Math.sin(frame * 0.3 + i)) * 0.25;
            return (
              <g key={i} transform={`translate(${sx} ${sy}) scale(${late})`}>
                <circle r={4.4} fill={MUNDO.vino} />
                <text y={0.5} fontSize={6} fontWeight={900} fill="#fff" textAnchor="middle" dominantBaseline="central">!</text>
              </g>
            );
          })}
        </g>
      ) : (
        <Entra t={t} fps={fps} orden={1}>
          {[66, 60, 54, 48].map((zz, i) => (
            <g key={zz}>
              <RectY Y={96.6} x0={92} x1={140} z0={zz - 2.5} z1={zz + 2.5} f={i === 0 ? "#f6e8ea" : "#f3f1ec"} />
              <circle cx={iso(95.5, 96.7, zz)[0]} cy={iso(95.5, 96.7, zz)[1]} r={2} fill={i === 0 ? MUNDO.vino : "#9a948a"} />
              <Linea a={[99, 96.7, zz]} b={[i === 0 ? 128 : 120, 96.7, zz]} s={i === 0 ? MUNDO.vino : "#b8b2a6"} sw={1.4} />
              <TextoPlanoY x={136} Y={96.8} z={zz} texto="✓" size={5} color={MUNDO.vino} peso={900} />
            </g>
          ))}
        </Entra>
      )}
      {caos ? (
        <Entra t={t} fps={fps} orden={1}>
          {[66, 150].map((xx, k) =>
            [0, 1, 2, 3, 4, 5].map((i) => (
              <Caja key={`${xx}-${i}`} x={xx + (i % 2) * 1.5} y={88 + k * 4} z={32 + i * 4} w={18} d={24} h={4} c={tono("#f6f2ea", "#9a948a")} sw={0.6} />
            )),
          )}
          <Caja x={150} y={108} z={32} w={10} d={12} h={4} c={tono("#2f2f35")} />
          {[0, 1].map((i) => {
            const [sx, sy] = iso(155, 114, 42);
            const r = 8 + i * 6 + (frame % 12) * 0.5;
            return <path key={i} d={`M ${sx - r} ${sy - r * 0.3} A ${r} ${r} 0 0 1 ${sx + r} ${sy - r * 0.3}`} stroke={MUNDO.vino} strokeWidth={1.6} fill="none" opacity={1 - (frame % 12) / 14} />;
          })}
          <Cilindro x={196} y={150} r={8} h={16} c={tono("#9a948a")} />
          <BolaPapel x={196} y={150} z={16} />
          <BolaPapel x={186} y={164} />
          <BolaPapel x={176} y={152} />
        </Entra>
      ) : (
        <Entra t={t} fps={fps} orden={2}>
          <Cilindro x={160} y={100} z={32} r={4} h={7} c={tono("#ffffff")} />
          <Planta x={186} y={160} alto={36} />
          <Caja x={70} y={96} z={32} w={14} d={18} h={2} c={tono("#e9e2d3")} sw={0.6} />
        </Entra>
      )}
      <Persona x={114} y={138} semilla={9} sentada cabizbaja={caos} ropa={caos ? "#3f5163" : MUNDO.vino} />
      {/* Segundo puesto */}
      <Mesa x={30} y={150} w={64} d={30} h={32} color="#d8c3a0" />
      <Caja x={50} y={154} z={32} w={30} d={3} h={20} c={tono("#2f2f35")} />
      <RectY Y={157.2} x0={52} x1={78} z0={34} z1={50} f={caos ? "#1c1c20" : "#f3f1ec"} />
      {/* Correos entrando solos a la pantalla (automatización) */}
      {!caos
        ? [0, 1, 2].map((i) => {
            const ciclo = (frame + i * 18) % 54;
            const k = ciclo / 54;
            const [ax, ay] = iso(200, 0, 80);
            const [bx, by] = iso(116, 96, 58);
            const sx = ax + (bx - ax) * k;
            const sy = ay + (by - ay) * k - Math.sin(k * Math.PI) * 30;
            return <Sobre key={i} sx={sx} sy={sy} escala={1 - k * 0.4} />;
          })
        : null}
    </g>
  );
};

export const INTERIORES = {
  taller: InteriorTaller,
  obra: InteriorObra,
  estudio: InteriorEstudio,
  oficina: InteriorOficina,
} as const;

export type NombreNicho = keyof typeof INTERIORES;

/** Puntos de interés por nicho, en coordenadas locales del lote. La cámara y los tooltips apuntan aquí. */
export const ANCLAS: Record<NombreNicho, Record<string, [number, number, number]>> = {
  taller: {
    centro: [110, 100, 30],
    mesa: [92, 70, 44],
    pared: [72, 4, 82],
    ficha: [60, 4, 82],
    audios: [140, 68, 60],
    maquinas: [70, 140, 36],
    perchero: [180, 26, 52],
    maniqui: [182, 150, 56],
    lote: [186, 180, 20],
    persona: [95, 104, 40],
  },
  obra: {
    centro: [110, 100, 30],
    pared: [60, 4, 60],
    andamio: [155, 30, 50],
    plano: [66, 134, 36],
    sala: [112, 70, 26],
    sofa: [110, 40, 24],
    ventana: [170, 4, 72],
    persona: [70, 162, 40],
    cables: [2, 70, 64],
  },
  estudio: {
    centro: [110, 100, 30],
    inventario: [160, 30, 34],
    producto: [110, 44, 42],
    luces: [60, 44, 70],
    celular: [96, 150, 60],
    camara: [112, 132, 48],
    pantalla: [24, 145, 46],
    ropa: [36, 172, 6],
    persona: [96, 150, 40],
  },
  oficina: {
    centro: [110, 100, 30],
    escritorio: [116, 102, 36],
    pantalla: [116, 96, 58],
    agenda: [74, 4, 80],
    calendario: [74, 4, 80],
    telefono: [155, 112, 40],
    papeles: [80, 96, 46],
    persona: [114, 138, 40],
    correo: [116, 96, 58],
  },
};
