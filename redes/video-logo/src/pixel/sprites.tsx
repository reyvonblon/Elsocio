/**
 * Sprites orgánicos: solo lo que NO es una caja se escribe celda por celda.
 * Cada letra es una entrada de la paleta; un punto es transparente.
 *
 * El Socio conserva su identidad del logo (`Socio.tsx`): sombrero de ala blanca ancha con cinta
 * vino, gafas de doble trazo, mostacho de puntas enrolladas, traje negro y corbata vino. A esta
 * resolución esa silueta es una ventaja: ala blanca + corbata roja se reconocen en un cuadro de
 * 24 píxeles de ancho, que es exactamente lo que un dibujo detallado no logra.
 */

import type { Sprite } from "./lienzo";

const PAL_SOCIO: Record<string, string> = {
  K: "#15151a", // traje y charol
  n: "#2e2e38", // costura del brazo
  W: "#f3ead7", // ala del sombrero y camisa
  w: "#cdc2a9", // sombra del ala
  S: "#e0b48c", // piel
  s: "#c58c63", // sombra de piel
  L: "#9fb0bb", // lente
  R: "#9c1c2e", // corbata y cinta del sombrero
  r: "#68101d", // punta de la corbata
};

/** El Socio de pie, 24 x 44. */
export const SOCIO: Sprite = {
  paleta: PAL_SOCIO,
  lineas: [
    ".......KKKKKKKKKK.......",
    "......KKKKKKKKKKKK......",
    "......KKKKKKKKKKKK......",
    "......RRRRRRRRRRRR......",
    "..WWWWWWWWWWWWWWWWWWWW..",
    "..wwWWWWWWWWWWWWWWWWww..",
    "...wwwwwwwwwwwwwwwwww...",
    ".....SSSSSSSSSSSSSS.....",
    ".....SSSSSSSSSSSSSS.....",
    ".....KKKKKKKKKKKKKK.....",
    ".....KLLLKKSSKKLLLK.....",
    ".....KLLLKSSSSKLLLK.....",
    ".....KKKKKSSSSKKKKK.....",
    ".....SSSSSSsSSSSSSS.....",
    ".....SSSSSSssSSSSSS.....",
    "........KKKKKKKK........",
    ".......KKKKKKKKKK.......",
    "......SSSSSSSSSSSS......",
    "........SSSSSSSS........",
    ".......WWWRRRRWWW.......",
    "...KKKKKKKWRRWKKKKKKK...",
    "...KKnKKKKWRRWKKKKnKK...",
    "...KKnKKKKWRRWKKKKnKK...",
    "...KKnKKKKWRRWKKKKnKK...",
    "...KKnKKKKWRRWKKKKnKK...",
    "...KKnKKKKWRRWKKKKnKK...",
    "...KKnKKKKWRRWKKKKnKK...",
    "...KKKKKKKKRRKKKKKKKK...",
    "...KKKKKKKKrrKKKKKKKK...",
    ".....KKKKKKKKKKKKKK.....",
    ".......KKKK..KKKK.......",
    ".......KKKK..KKKK.......",
    ".......KKKK..KKKK.......",
    ".......KKKK..KKKK.......",
    ".......KKKK..KKKK.......",
    ".......KKKK..KKKK.......",
    ".......KKKK..KKKK.......",
    ".......KKKK..KKKK.......",
    ".......KKKK..KKKK.......",
    ".......KKKK..KKKK.......",
    ".......KKKK..KKKK.......",
    "......nKKKK..KKKKn......",
    "......KKKKK..KKKKK......",
    "......KKKKK..KKKKK......",
  ],
};

/** Brazo extendido: se estampa aparte para no rehacer el sprete entero por cada pose. */
export const BRAZO_SENALA: Sprite = {
  paleta: PAL_SOCIO,
  lineas: ["KKK.", "KKKK", ".KKK", "..SS"],
};

/**
 * Un cliente cualquiera, 20 x 34. La `A` es la camisa: se cambia por nicho desde la escena, así
 * que el mismo sprite sirve para el dueño del taller, la del e-commerce o el de la agencia.
 */
export const CLIENTE: Sprite = {
  paleta: {
    H: "#2b2420",
    S: "#e0b48c",
    s: "#c58c63",
    K: "#15151a",
    A: "#3f5163",
    a: "#30404f",
    J: "#4a5668",
    P: "#2f3a46",
  },
  lineas: [
    "....HHHHHHHHHHHH....",
    "....HHHHHHHHHHHH....",
    "....HHSSSSSSSSHH....",
    "....HSSSSSSSSSSH....",
    "....SSKKSSSSKKSS....",
    "....SSSSSSSSSSSS....",
    "....SSSSSKKSSSSS....",
    ".....SSSSSSSSSS.....",
    "......SSSSSSSS......",
    "........SSSS........",
    "..AAAAAAAAAAAAAAAA..",
    "..AAaAAAAAAAAAAaAA..",
    "..AAaAAAAAAAAAAaAA..",
    "..AAaAAAAAAAAAAaAA..",
    "..AAaAAAAAAAAAAaAA..",
    "..AAaAAAAAAAAAAaAA..",
    "..AAaAAAAAAAAAAaAA..",
    "..AAaAAAAAAAAAAaAA..",
    "..AAaAAAAAAAAAAaAA..",
    "....JJJJJJJJJJJJ....",
    "....JJJJJJJJJJJJ....",
    ".....JJJJ..JJJJ.....",
    ".....JJJJ..JJJJ.....",
    ".....JJJJ..JJJJ.....",
    ".....JJJJ..JJJJ.....",
    ".....JJJJ..JJJJ.....",
    ".....JJJJ..JJJJ.....",
    ".....JJJJ..JJJJ.....",
    ".....JJJJ..JJJJ.....",
    ".....PPPP..PPPP.....",
    ".....PPPP..PPPP.....",
    "....KKKKK..KKKKK....",
    "....KKKKK..KKKKK....",
    "....KKKKK..KKKKK....",
  ],
};

/** Mata en matera, 14 x 20. Rompe las líneas rectas de los muebles: sin algo orgánico se ve a CAD. */
export const MATA: Sprite = {
  paleta: { G: "#86996d", g: "#657a52", h: "#9aae80", t: "#7d7266", P: "#b4623c", p: "#8c4529" },
  lineas: [
    "......hh......",
    ".....hhhG.....",
    "....hhhhGG....",
    "...hhhhhGGG...",
    "..hhhhhhGGgG..",
    ".hhhhhhGGggggg",
    "hhhhhhGGgggggg",
    ".hhhhGGggggggg",
    "..hhGGGgggggg.",
    "...GGGGgggggg.",
    "....GGGggggg..",
    ".....GGgggg...",
    "......tt......",
    "......tt......",
    "....PPPPPP....",
    "...PPPPPPPP...",
    "...PPPPPPPP...",
    "....PPPPPP....",
    "....pppppp....",
    ".....pppp.....",
  ],
};

/** Percha de ropa colgada (nicho de confección), 18 x 22. */
export const PERCHA: Sprite = {
  paleta: { b: "#8d8578", R: "#9c1c2e", A: "#3f5163", W: "#e9e2d3", D: "#d9a441", k: "#6b6358" },
  lineas: [
    "bbbbbbbbbbbbbbbbbb",
    "..b....b....b...b.",
    ".RRR..AAA..WWW.DDD",
    ".RRR..AAA..WWW.DDD",
    ".RRR..AAA..WWW.DDD",
    ".RRR..AAA..WWW.DDD",
    ".RRR..AAA..WWW.DDD",
    ".RRR..AAA..WWW.DDD",
    ".RRR..AAA..WWW.DDD",
    "..R....A....W...D.",
    "........k.........",
    "........k.........",
    "........k.........",
    "........k.........",
    "........k.........",
    "........k.........",
    "........k.........",
    "........k.........",
    "........k.........",
    "........k.........",
    ".....kkkkkkk......",
    "....kkkkkkkkk.....",
  ],
};


/** Árbol, 22 x 29. La copa es un volumen con sombra, no un rombo: un arbusto ampliado se ve plano. */
export const ARBOL: Sprite = {
  paleta: { G: "#86996d", g: "#657a52", h: "#9aae80", t: "#8a6a4a", T: "#63492f" },
  lineas: [
    "........GGGGGG........",
    "......GGhhhhGGGG......",
    ".....GGhhhhhhGGGG.....",
    "....GGhhhhhhhhGGGG....",
    "...GGhhhhhhhhhGGGGG...",
    "..GGhhhhhhhhhGGGGGGG..",
    "..GGhhhhhhhhGGGGGgGG..",
    ".GGGhhhhhhhGGGGGgggGG.",
    ".GGGGhhhhhGGGGGgggggG.",
    ".GGGGGhhhGGGGGgggggggG",
    ".GGGGGGGGGGGGgggggggg.",
    "..GGGGGGGGGGggggggggg.",
    "..GGGGGGGGGgggggggg...",
    "...GGGGGGGgggggggg....",
    "....GGGGGggggggg......",
    ".....GGGGgggggg.......",
    "......GGGggggg........",
    ".........ttTT.........",
    ".........ttTT.........",
    ".........ttTT.........",
    ".........ttTT.........",
    ".........ttTT.........",
    ".........ttTT.........",
    ".........ttTT.........",
    ".........ttTT.........",
    ".........ttTT.........",
    "........tttTTT........",
    ".......tttTTTTT.......",
    "......tttTTTTTTT......",
  ],
};

/** Arbusto suelto, 14 x 9: para exteriores, donde una matera de barro no tiene sentido. */
export const ARBUSTO: Sprite = {
  paleta: { G: "#86996d", g: "#657a52", h: "#9aae80" },
  lineas: [
    "....GGhhhh....",
    "..GGhhhhhhGG..",
    ".GGhhhhhhhGGG.",
    "GGhhhhhhhGGggG",
    "GGhhhhhhGGgggg",
    "GGGhhhhGGggggg",
    ".GGGGGGGggggg.",
    "..GGGGGgggggg.",
    "....GGGgggg...",
  ],
};
