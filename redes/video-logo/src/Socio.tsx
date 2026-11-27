import React from "react";
import { useCurrentFrame } from "remotion";
import { MUNDO } from "./mundo/base";

/**
 * El Socio como PERSONAJE, no como mascota de esquina.
 *
 * Nace de la propuesta de Raymond (2026-11-26): si el personaje de la marca es el protagonista, el
 * reel deja de ser una postal con texto encima y pasa a ser alguien contando algo. Eso ataca de
 * raíz el techo que encontramos midiendo: en el formato isométrico las personas miden 65 px, y en
 * el collage la mascota ocupaba el 0,01% del cuadro — podíamos animarle la boca a 4 ciclos por
 * segundo y no se notaba ni se medía (guía §15.1). El movimiento nunca fue el problema: el tamaño sí.
 *
 * Silueta: alto y delgado, traje negro, corbata roja larga y zapatos de charol — un Hombre de
 * Negro con la corbata de la marca. La cabeza va calcada del logo (`redes/avatar_personaje.html`):
 * REDONDA, ala blanca ancha, gafas de doble trazo y mostacho de puntas enrolladas. Sin boca: el
 * logo no tiene, y el que habla es el bigote.
 *
 * El relieve (degradados, doble contorno, brillos) no es adorno: con formas planas de un tono el
 * personaje se leía como South Park. El logo original ya usa degradados en sombrero, cabeza y
 * mostacho, y es lo que lo hace ver acabado.
 *
 * Mecánicas de la referencia MOKO (guía §15): el cuerpo entero se mueve siempre y cada eje va a su
 * frecuencia. Lo que NO se toma: estética gamer (HUD, barras de vida, neón), descartada en §4.
 */

const NEGRO = "#15151a";
const CAMISA = "#f3ead7";
const CHAROL = "#0c0c10";

export type PoseSocio = "habla" | "senala" | "piensa" | "celebra" | "camina";

export const Socio: React.FC<{
  /** Alto en px. A 1180 ocupa ~60% del cuadro de 1920 (regla 2 de §15). */
  alto?: number;
  pose?: PoseSocio;
  mira?: 1 | -1;
  frame?: number;
}> = ({ alto = 1180, pose = "habla", mira = 1, frame: frameProp }) => {
  const f = useCurrentFrame();
  const frame = frameProp ?? f;

  // Un eje por parte, cada uno con su frecuencia: si todo oscila al mismo compás parece un muñeco.
  const habla = pose === "habla" || pose === "senala" || pose === "celebra";
  // El mostacho hace de boca: 0 cerrado, 1 abierto. Mismo ritmo que la boca de MOKO (~7 frames).
  const bigote = habla ? (Math.sin(frame * 0.9) > 0.1 ? 1 : 0) : 0;
  const respira = Math.sin(frame * 0.5) * 2.6;
  const ladea = Math.sin(frame * 0.23) * 2.2;
  const asiente = Math.sin(frame * 0.47) * 3;
  const zancada = pose === "camina" ? Math.sin(frame * 0.42) : 0;
  const brinco =
    pose === "celebra" ? Math.abs(Math.sin(frame * 0.3)) * 22
      : pose === "camina" ? Math.abs(Math.sin(frame * 0.84)) * 6
        : 0;

  const brazoDer =
    pose === "senala" ? -74 + Math.sin(frame * 0.5) * 4
      : pose === "celebra" ? -148 + Math.sin(frame * 0.55) * 18
        : pose === "piensa" ? -52
          : pose === "camina" ? zancada * 30
            : Math.sin(frame * 0.38) * 16 - 6;
  const brazoIzq =
    pose === "celebra" ? 148 + Math.sin(frame * 0.55 + 1.4) * 18
      : pose === "camina" ? -zancada * 30
        : Math.sin(frame * 0.38 + 1.7) * 11 + 5;
  const corbata = Math.sin(frame * 0.33) * 3 - brinco * 0.5;

  // El mostacho como FORMA rellena, no como trazo: un stroke grueso tumbado se leía como una
  // boca gigante. Un bigote real es ancho bajo la nariz y se afina hacia las puntas, que se
  // enroscan hacia arriba. Al hablar baja el centro y suben las puntas.
  const alaBigote = (lado: 1 | -1) => {
    const b = bigote;
    const x = (v: number) => 110 + lado * v;
    return `M 110 ${118 + b * 6}
      C ${x(10)} ${128 + b * 4} ${x(24)} ${131 + b * 2} ${x(34)} ${126 - b * 3}
      C ${x(40)} ${122 - b * 4} ${x(40)} ${113 - b * 3} ${x(33)} ${111 - b * 3}
      C ${x(28)} ${110 - b * 3} ${x(26)} ${115 - b * 3} ${x(29)} ${117 - b * 3}
      C ${x(22)} ${119 - b * 2} ${x(12)} ${114 + b} 110 ${107 + b * 6} Z`;
  };

  const cuerpo = (
    <>
      {/* ---------------- piernas, pantalón de traje ---------------- */}
      <g transform={`rotate(${zancada * 11} 100 300)`}>
        <rect x={76} y={296} width={25} height={132} rx={9} fill="url(#socioPierna)" />
        <rect x={86} y={300} width={1.8} height={124} fill="#ffffff" opacity={0.18} />
        <rect x={76.5} y={300} width={2.2} height={124} rx={1.1} fill="#ffffff" opacity={0.14} />
        <path d="M 72 428 L 101 428 L 104 446 Q 104 452 97 452 L 68 452 Q 64 452 64 446 Z" fill={CHAROL} />
        <ellipse cx={82} cy={436} rx={11} ry={3.4} fill="#ffffff" opacity={0.5} />
      </g>
      <g transform={`rotate(${-zancada * 11} 120 300)`}>
        <rect x={119} y={296} width={25} height={132} rx={9} fill="url(#socioPierna)" />
        <rect x={129} y={300} width={1.8} height={124} fill="#ffffff" opacity={0.12} />
        <path d="M 116 428 L 145 428 L 148 446 Q 148 452 141 452 L 112 452 Q 108 452 108 446 Z" fill={CHAROL} />
        <ellipse cx={126} cy={436} rx={11} ry={3.4} fill="#ffffff" opacity={0.42} />
      </g>

      {/* ---------------- brazos, detrás del saco ---------------- */}
      <g transform={`rotate(${brazoIzq} 72 162)`}>
        <rect x={62} y={156} width={21} height={136} rx={10} fill="url(#socioManga)" />
        <rect x={62.5} y={158} width={2.6} height={128} rx={1.3} fill="#ffffff" opacity={0.22} />
        <rect x={62} y={276} width={21} height={9} rx={3} fill={CAMISA} />
        <circle cx={72} cy={292} r={8.5} fill="url(#socioMano)" />
      </g>
      <g transform={`rotate(${brazoDer} 148 162)`}>
        <rect x={138} y={156} width={21} height={136} rx={10} fill="url(#socioManga)" />
        <rect x={138.5} y={158} width={2.6} height={128} rx={1.3} fill="#ffffff" opacity={0.16} />
        <rect x={138} y={276} width={21} height={9} rx={3} fill={CAMISA} />
        <circle cx={148} cy={292} r={8.5} fill="url(#socioMano)" />
      </g>

      {/* ---------------- torso: saco con solapas ---------------- */}
      <g transform={`translate(0 ${respira * 0.35})`}>
        <rect x={86} y={150} width={48} height={120} fill={CAMISA} />
        <path d="M 74 152 Q 62 158 62 196 L 62 300 Q 62 308 72 308 L 96 308 L 96 212 Z" fill="url(#socioSaco)" />
        <path d="M 146 152 Q 158 158 158 196 L 158 300 Q 158 308 148 308 L 124 308 L 124 212 Z" fill="url(#socioSaco)" />
        <path d="M 74 152 L 110 150 L 96 212 L 74 206 Z" fill="url(#socioSolapa)" />
        <path d="M 146 152 L 110 150 L 124 212 L 146 206 Z" fill="url(#socioSolapa)" />
        {/* Luz de canto: sin esto el traje negro se funde con el fondo oscuro y el cuerpo
            desaparece — la cabeza quedaba flotando. Es el borde que lo recorta. */}
        <path d="M 74 152 Q 62 158 62 196 L 62 300" stroke="#ffffff" strokeWidth={2.4} fill="none" opacity={0.3} strokeLinecap="round" />
        <path d="M 146 152 Q 158 158 158 196 L 158 300" stroke="#ffffff" strokeWidth={1.8} fill="none" opacity={0.16} strokeLinecap="round" />
        {/* costura de las solapas */}
        <path d="M 76 156 L 96 210" stroke="#ffffff" strokeWidth={1.1} opacity={0.22} fill="none" />
        <path d="M 144 156 L 124 210" stroke="#ffffff" strokeWidth={1.1} opacity={0.14} fill="none" />
        {/* pañuelo en el bolsillo del pecho */}
        <path d="M 130 196 L 146 193 L 145 201 L 131 203 Z" fill={CAMISA} opacity={0.9} />
        <path d="M 133 196 L 137 190 L 141 196 Z" fill="#ffffff" />
        {/* botones */}
        <circle cx={96} cy={236} r={3.4} fill="#3b3b47" stroke="#07070a" strokeWidth={0.9} />
        <circle cx={96} cy={262} r={3.4} fill="#3b3b47" stroke="#07070a" strokeWidth={0.9} />
        <g transform={`rotate(${corbata * 0.6} 110 160)`}>
          <path d="M 104 150 L 116 150 L 119 166 L 110 174 L 101 166 Z" fill="url(#socioCorbata)" />
          <path d="M 103 170 L 117 170 L 121 254 L 110 268 L 99 254 Z" fill="url(#socioCorbata)" />
          <path d="M 106 174 L 110 174 L 110 262 L 107 256 Z" fill="#ffffff" opacity={0.14} />
        </g>
      </g>

      {/* ---------------- cabeza: calcada del logo ---------------- */}
      <g transform={`translate(${ladea} ${-respira + asiente}) rotate(${ladea * 0.45} 110 92)`}>
        {/* REDONDA, con la luz arriba-izquierda del radial del logo */}
        <circle cx={110} cy={92} r={66} fill="url(#socioCabeza)" />
        <ellipse cx={86} cy={62} rx={30} ry={20} fill="#ffffff" opacity={0.07} transform="rotate(-28 86 62)" />
        {/* copa de seda: degradado + raya de brillo */}
        <rect x={82} y={-22} width={56} height={50} rx={3} fill="url(#socioSeda)" />
        <rect x={88} y={-16} width={4} height={30} rx={2} fill="#ffffff" opacity={0.32} />
        <rect x={82} y={22} width={56} height={6} fill={CAMISA} />
        {/* sombra del ala sobre la frente: sin esto el sombrero parece pegado con cinta */}
        <path d="M 54 36 Q 110 60 166 36 L 166 46 Q 110 72 54 46 Z" fill="#000000" opacity={0.3} />
        {/* ala blanca y ancha: lo que identifica al logo de lejos */}
        <ellipse cx={110} cy={30} rx={80} ry={11} fill="#ffffff" />
        <ellipse cx={110} cy={32} rx={80} ry={10} fill={CAMISA} opacity={0.75} />
        {/* Gafas: cristal + montura con borde interior y exterior. Antes eran un círculo con
            stroke y se leían como dibujadas a lápiz; una montura real tiene grosor y canto. */}
        {[82, 138].map((cx) => (
          <g key={cx}>
            <circle cx={cx} cy={84} r={20} fill="url(#socioCristal)" />
            <circle cx={cx} cy={84} r={22} fill="none" stroke="url(#socioMarco)" strokeWidth={7} />
            <circle cx={cx} cy={84} r={25.8} fill="none" stroke="#07070a" strokeWidth={2.2} />
            <circle cx={cx} cy={84} r={18.4} fill="none" stroke="#07070a" strokeWidth={1.8} />
          </g>
        ))}
        {/* puente y patillas, con el mismo canto */}
        <g fill="none" strokeLinecap="round">
          <path d="M 104 80 Q 110 73 116 80" stroke="#07070a" strokeWidth={9} />
          <path d="M 104 80 Q 110 73 116 80" stroke="url(#socioMarco)" strokeWidth={5.5} />
          <line x1={58} y1={80} x2={45} y2={76} stroke="#07070a" strokeWidth={9} />
          <line x1={58} y1={80} x2={45} y2={76} stroke="url(#socioMarco)" strokeWidth={5.5} />
          <line x1={162} y1={80} x2={175} y2={76} stroke="#07070a" strokeWidth={9} />
          <line x1={162} y1={80} x2={175} y2={76} stroke="url(#socioMarco)" strokeWidth={5.5} />
        </g>
        {/* reflejo en el cristal */}
        <path d="M 70 76 Q 78 68 88 72" stroke="#ffffff" strokeWidth={3.4} fill="none" opacity={0.5} strokeLinecap="round" />
        <path d="M 126 76 Q 134 68 144 72" stroke="#ffffff" strokeWidth={3.4} fill="none" opacity={0.34} strokeLinecap="round" />
        {/* mostacho: forma rellena con contorno. Es la boca (el logo no tiene boca). */}
        <g stroke="#07070a" strokeWidth={3} strokeLinejoin="round">
          <path d={alaBigote(-1)} fill="url(#socioBigote)" />
          <path d={alaBigote(1)} fill="url(#socioBigote)" />
        </g>
      </g>
    </>
  );

  const ancho = (alto * 220) / 470;
  return (
    <svg width={ancho} height={alto} viewBox="0 0 220 470" style={{ overflow: "visible", transform: `translateY(${-brinco}px) scaleX(${mira})` }}>
      <defs>
        <radialGradient id="socioCabeza" cx="36%" cy="28%" r="78%">
          <stop offset="0%" stopColor="#3c3c48" />
          <stop offset="52%" stopColor="#1d1d25" />
          <stop offset="100%" stopColor="#09090d" />
        </radialGradient>
        <linearGradient id="socioSeda" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#16161d" />
          <stop offset="20%" stopColor="#363642" />
          <stop offset="46%" stopColor="#14141a" />
          <stop offset="100%" stopColor="#08080c" />
        </linearGradient>
        <radialGradient id="socioCristal" cx="34%" cy="28%" r="80%">
          <stop offset="0%" stopColor="#4a4a58" />
          <stop offset="60%" stopColor="#22222b" />
          <stop offset="100%" stopColor="#0d0d12" />
        </radialGradient>
        <linearGradient id="socioMarco" x1="0" y1="0" x2="0.4" y2="1">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="45%" stopColor="#efe7d4" />
          <stop offset="100%" stopColor="#b3aa96" />
        </linearGradient>
        <linearGradient id="socioBigote" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="100%" stopColor="#cdc5b2" />
        </linearGradient>
        <linearGradient id="socioSaco" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#272733" />
          <stop offset="55%" stopColor="#15151b" />
          <stop offset="100%" stopColor="#0b0b10" />
        </linearGradient>
        <linearGradient id="socioSolapa" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#30303d" />
          <stop offset="100%" stopColor="#101016" />
        </linearGradient>
        <linearGradient id="socioManga" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#3a3a48" />
          <stop offset="70%" stopColor="#1e1e27" />
          <stop offset="100%" stopColor="#13131a" />
        </linearGradient>
        <linearGradient id="socioPierna" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#262632" />
          <stop offset="70%" stopColor="#111117" />
          <stop offset="100%" stopColor="#0a0a0e" />
        </linearGradient>
        <radialGradient id="socioMano" cx="35%" cy="30%" r="80%">
          <stop offset="0%" stopColor="#f0cba6" />
          <stop offset="100%" stopColor="#c99a72" />
        </radialGradient>
        <linearGradient id="socioCorbata" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#b8293c" />
          <stop offset="48%" stopColor={MUNDO.vino} />
          <stop offset="100%" stopColor="#5e0f1a" />
        </linearGradient>
      </defs>
      {/* Sin copia de sombra: con formas planas funcionaba, pero sobre degradados se veía como
          un fantasma duplicado detrás de la cabeza y del ala. El personaje ya se separa del fondo
          por su propio contraste. La sombra va al suelo, en la escena, no pegada al cuerpo. */}
      {/* Contorno finísimo, SOLO como trazo detrás: recorta la silueta del fondo. Antes el cuerpo
          se dibujaba una única vez dentro de este grupo, que lleva opacity 0.5 — es decir, el
          personaje entero salía al 50% de opacidad y se transparentaba sobre el fondo. */}
      <g stroke={NEGRO} strokeWidth={2.4} strokeLinejoin="round" opacity={0.45} paintOrder="stroke" fill="none">
        {cuerpo}
      </g>
      {/* el personaje, opaco */}
      {cuerpo}
    </svg>
  );
};
