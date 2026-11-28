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

// ---------------------------------------------------------------- utilería del taller
// Objetos que entran y salen durante el capítulo. Son los que cuentan la historia: sin algo
// que cambie de estado en pantalla, el plano está muerto por mucho que la cámara se mueva.

/** Bolsa de tela que trae el cliente, 12 x 14. */
export const BOLSA: Sprite = {
  paleta: { a: "#b8a98f", A: "#cdbfa5", k: "#6d6354", R: "#9c1c2e" },
  lineas: [
    "..k........k",
    "..k........k",
    ".kAk......kk",
    ".AAAk....kAA",
    "AAAAAkkkAAAA",
    "AAAAAAAAAAAA",
    "AAAARRRRAAAA",
    "AAAARRRRAAAA",
    "AAAAAAAAAAAA",
    "aAAAAAAAAAAa",
    "aAAAAAAAAAAa",
    "aaAAAAAAAAaa",
    "aaaAAAAAAaaa",
    "aaaaaaaaaaaa",
  ],
};

/** Prenda extendida sobre la mesa, 18 x 14. Es "la muestra" que salió mal. */
export const PRENDA: Sprite = {
  paleta: { T: "#4e6a86", t: "#3c5368", W: "#e9e2d3", k: "#2b3b4a" },
  lineas: [
    "...kkk......kkk...",
    "..kTTTk....kTTTk..",
    ".kTTTTTkkkkTTTTTk.",
    "kTTTTTTTWWTTTTTTTk",
    "kTTTTTTWWWWTTTTTTk",
    ".kTTTTTTWWTTTTTTk.",
    "..kTTTTTTTTTTTTk..",
    "..kTTTTTTTTTTTTk..",
    "...kTTTTTTTTTTk...",
    "...kTTTTTTTTTTk...",
    "...kTTTTTTTTTTk...",
    "...kTTTTTTTTTTk...",
    "...kttttttttttk...",
    "....kkkkkkkkkk....",
  ],
};

/** Maniquí de costura, 14 x 34. Lo que hace que un cuarto se lea como taller y no como oficina. */
export const MANIQUI: Sprite = {
  paleta: { M: "#d9cdb4", m: "#b9ab8e", k: "#6d6354", p: "#8d8578" },
  lineas: [
    "....MMMMMM....",
    "...MMMMMMMM...",
    "..MMMMMMMMMM..",
    "..MMMMMMMmmM..",
    ".MMMMMMMMmmmM.",
    ".MMMMMMMMmmmM.",
    "MMMMMMMMMmmmmM",
    "MMMMMMMMMmmmmM",
    "MMMMMMMMMmmmmM",
    "MMMMMMMMMmmmmM",
    ".MMMMMMMMmmmM.",
    ".MMMMMMMMmmmM.",
    ".MMMMMMMMmmmM.",
    "..MMMMMMMmmM..",
    "..MMMMMMMmmM..",
    "...MMMMMMmM...",
    "...MMMMMMmM...",
    "....MMMMmM....",
    "....kkkkkk....",
    "......kk......",
    "......kk......",
    "......kk......",
    "......kk......",
    "......kk......",
    "......kk......",
    "......kk......",
    "......kk......",
    "......kk......",
    "......kk......",
    "......kk......",
    ".....pppp.....",
    "....pppppp....",
    "...pppppppp...",
    "....pppppp....",
  ],
};

/** Ficha técnica: el objeto que resuelve el capítulo. 16 x 20. */
export const FICHA: Sprite = {
  paleta: { W: "#f6f1e4", g: "#9aa7b4", k: "#3a4450", R: "#9c1c2e", b: "#c9c2b0" },
  lineas: [
    "WWWWWWWWWWWWWWWW",
    "WkkkkkkWWRRRRRWW",
    "WWWWWWWWWWWWWWWW",
    "WWggggggggggWWWW",
    "WWg........gWWWW",
    "WWg..gggg..gWWWW",
    "WWg..g..g..gWWWW",
    "WWg..g..g..gWWWW",
    "WWg..gggg..gWWWW",
    "WWg........gWWWW",
    "WWggggggggggWWWW",
    "WWWWWWWWWWWWWWWW",
    "WkkkkkWWkkkkkWWW",
    "WWWWWWWWWWWWWWWW",
    "WkkkkkkkWWkkkWWW",
    "WWWWWWWWWWWWWWWW",
    "WkkkkWWkkkkkkWWW",
    "WWWWWWWWWWWWWWWW",
    "WWWWWWWWWWWWWWWW",
    "bbbbbbbbbbbbbbbb",
  ],
};

/** Rollos de tela apilados, 18 x 12. Relleno de taller: sin esto el cuarto se ve a estreno. */
export const ROLLOS: Sprite = {
  paleta: { R: "#9c1c2e", A: "#3f5163", D: "#d9a441", V: "#5f7a5c", k: "#4a4036", W: "#e9e2d3" },
  lineas: [
    ".....RRRRRRRR.....",
    "....RRRRRRRRRR....",
    "...kRRRRRRRRRRk...",
    "...AAAAAAAAAAAA...",
    "..AAAAAAAAAAAAAA..",
    "..kAAAAAAAAAAAAk..",
    "..DDDDDDDDDDDDDD..",
    ".DDDDDDDDDDDDDDDD.",
    ".kDDDDDDDDDDDDDDk.",
    ".WWWWWWWWWWWWWWWW.",
    "VVVVVVVVVVVVVVVVVV",
    "kVVVVVVVVVVVVVVVVk",
  ],
};

/** Tijeras de sastre sobre la mesa, 12 x 7. */
export const TIJERAS: Sprite = {
  paleta: { m: "#b9b5ac", M: "#dcd8cf", k: "#2b2b30" },
  lineas: [
    "kk........kk",
    "kkk......kkk",
    ".kkk....kkk.",
    "..MmmmmmmM..",
    "...MmmmmM...",
    "....Mmmm....",
    ".....Mm.....",
  ],
};
