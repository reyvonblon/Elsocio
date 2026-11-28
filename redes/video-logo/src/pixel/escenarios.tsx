/**
 * Los escenarios de la serie. Cada uno es un OBJETO, no código dibujado.
 *
 * Son tres nichos, tres locaciones y tres tratamientos distintos a propósito: interior cálido
 * con damero (taller), interior en obra gris sin damero y con la cámara en espejo (apartamento),
 * y exterior al atardecer con horizonte de ciudad (azotea). Si el formato aguanta estos tres,
 * aguanta los 50 que pide Raymond; si se ven los tres iguales, el formato no sirve y se sabe hoy.
 */

import type { Habitacion } from "./escena";
import { ARBOL, ARBUSTO, CLIENTE, MANIQUI, MATA, PERCHA, ROLLOS, SOCIO, TIJERAS } from "./sprites";

/**
 * Nicho: fichas técnicas de ropa. Taller de confección, interior cálido.
 *
 * Denso a propósito. La primera versión tenía 3 muebles y Raymond lo leyó exactamente como lo
 * que era: "un cuadro con 2 personas ahí sin hacer nada". Un taller real está lleno — rollos
 * por el piso, retazos, cajas, el maniquí, la plancha — y esa acumulación es la mitad de lo
 * que hace que una sala en pixel art se vea terminada y no a estreno.
 */
export const TALLER: Habitacion = {
  nombre: "taller de confección",
  ti: 7,
  tj: 7,
  pisoA: "#d8ccb2",
  pisoB: "#c4b596",
  paredIzq: "#cdc1a6",
  paredDer: "#e3dac4",
  altoPared: 72,
  ventanas: [{ pared: "der", desde: 3.4, hasta: 5.2, z0: 30, z1: 62 }],
  muebles: [
    { tipo: "tapete", i: 2.0, j: 2.4, wi: 2.9, wj: 2.0, color: "#8d2435" },

    // --- pared izquierda (i=0): mesa de corte larga, máquina de coser y herramienta
    { tipo: "cubo", i: 0.25, j: 0.65, wi: 0.1, wj: 0.1, alto: 12, mat: "maderaOscura" },
    { tipo: "cubo", i: 1.05, j: 0.65, wi: 0.1, wj: 0.1, alto: 12, mat: "maderaOscura" },
    { tipo: "cubo", i: 0.25, j: 2.85, wi: 0.1, wj: 0.1, alto: 12, mat: "maderaOscura" },
    { tipo: "cubo", i: 1.05, j: 2.85, wi: 0.1, wj: 0.1, alto: 12, mat: "maderaOscura" },
    { tipo: "cubo", i: 0.2, j: 0.6, wi: 1.0, wj: 2.4, alto: 2, mat: "madera", base: 12 },
    { tipo: "cubo", i: 0.35, j: 0.72, wi: 0.6, wj: 0.5, alto: 3, mat: "blanco", base: 14 },
    { tipo: "cubo", i: 0.35, j: 1.3, wi: 0.6, wj: 0.26, alto: 2, mat: "vino", base: 14 },
    { tipo: "cubo", i: 0.35, j: 1.62, wi: 0.6, wj: 0.22, alto: 2, mat: "metal", base: 14 },
    { tipo: "cubo", i: 0.35, j: 2.05, wi: 0.6, wj: 0.65, alto: 4, mat: "tinta", base: 14 },
    { tipo: "cubo", i: 0.4, j: 2.1, wi: 0.45, wj: 0.16, alto: 5, mat: "tinta", base: 18 },
    { tipo: "sprite", sprite: TIJERAS, i: 0.7, j: 0.95, sube: 14 },
    // tablero de herramienta colgado
    { tipo: "cubo", i: 0.02, j: 3.5, wi: 0.06, wj: 1.3, alto: 16, mat: "maderaOscura", base: 34 },
    { tipo: "cubo", i: 0.02, j: 4.0, wi: 0.05, wj: 0.12, alto: 5, mat: "metal", base: 40 },
    { tipo: "cubo", i: 0.02, j: 4.3, wi: 0.05, wj: 0.12, alto: 7, mat: "metal", base: 40 },

    // --- pared derecha (j=0): repisas con lote, reloj y cuadro
    { tipo: "cubo", i: 1.5, j: 0.2, wi: 1.9, wj: 0.5, alto: 22, mat: "maderaOscura" },
    { tipo: "cubo", i: 1.6, j: 0.28, wi: 0.5, wj: 0.34, alto: 7, mat: "carton", base: 22 },
    { tipo: "cubo", i: 2.2, j: 0.28, wi: 0.5, wj: 0.34, alto: 10, mat: "carton", base: 22 },
    { tipo: "cubo", i: 2.8, j: 0.28, wi: 0.5, wj: 0.34, alto: 6, mat: "carton", base: 22 },
    { tipo: "cubo", i: 1.5, j: 0.2, wi: 1.9, wj: 0.45, alto: 2, mat: "maderaOscura", base: 36 },
    { tipo: "cubo", i: 1.7, j: 0.26, wi: 0.35, wj: 0.3, alto: 5, mat: "vino", base: 38 },
    { tipo: "cubo", i: 2.3, j: 0.26, wi: 0.35, wj: 0.3, alto: 5, mat: "blanco", base: 38 },
    { tipo: "cubo", i: 2.9, j: 0.26, wi: 0.35, wj: 0.3, alto: 5, mat: "metal", base: 38 },
    { tipo: "cubo", i: 6.0, j: 0.03, wi: 0.45, wj: 0.05, alto: 8, mat: "blanco", base: 48 },
    { tipo: "cubo", i: 1.1, j: 0.03, wi: 0.5, wj: 0.05, alto: 11, mat: "madera", base: 40 },

    // --- piso: lo que hace taller
    { tipo: "sprite", sprite: MANIQUI, i: 1.25, j: 4.6 },
    { tipo: "sprite", sprite: ROLLOS, i: 0.75, j: 5.9 },
    { tipo: "sprite", sprite: PERCHA, i: 0.6, j: 3.3 },
    { tipo: "sprite", sprite: MATA, i: 6.4, j: 2.1 },
    // mesa chica auxiliar
    { tipo: "cubo", i: 5.5, j: 0.9, wi: 0.75, wj: 0.75, alto: 11, mat: "madera" },
    { tipo: "cubo", i: 5.6, j: 1.0, wi: 0.5, wj: 0.5, alto: 4, mat: "carton", base: 11 },
    // taburete
    { tipo: "cubo", i: 3.9, j: 1.5, wi: 0.42, wj: 0.42, alto: 9, mat: "maderaOscura" },
    // cajas del lote en el piso
    { tipo: "cubo", i: 5.9, j: 3.3, wi: 0.72, wj: 0.72, alto: 9, mat: "carton" },
    { tipo: "cubo", i: 5.95, j: 3.35, wi: 0.62, wj: 0.62, alto: 8, mat: "carton", base: 9 },
    { tipo: "cubo", i: 5.2, j: 4.2, wi: 0.7, wj: 0.7, alto: 9, mat: "carton" },
    // caneca con retazos
    { tipo: "cubo", i: 2.9, j: 6.2, wi: 0.5, wj: 0.5, alto: 10, mat: "metal" },
    { tipo: "cubo", i: 2.98, j: 6.28, wi: 0.34, wj: 0.34, alto: 3, mat: "vino", base: 10 },
    // tabla de planchar
    { tipo: "cubo", i: 4.6, j: 5.9, wi: 1.1, wj: 0.38, alto: 2, mat: "blanco", base: 11 },
    { tipo: "cubo", i: 4.75, j: 6.0, wi: 0.08, wj: 0.08, alto: 11, mat: "metal" },
    { tipo: "cubo", i: 5.5, j: 6.0, wi: 0.08, wj: 0.08, alto: 11, mat: "metal" },
    { tipo: "cubo", i: 4.75, j: 5.95, wi: 0.3, wj: 0.26, alto: 4, mat: "tinta", base: 13 },
    // primer plano: cajas apiladas junto a la cámara (la capa de profundidad de §15 regla 3)
    { tipo: "cubo", i: 6.3, j: 6.1, wi: 0.85, wj: 0.85, alto: 12, mat: "carton" },
    { tipo: "cubo", i: 6.35, j: 6.15, wi: 0.75, wj: 0.75, alto: 10, mat: "carton", base: 12 },
  ],
};

/** Nicho: modelado 3D de espacios. Apartamento en obra gris, frío y vacío. Cámara en espejo. */
export const OBRA: Habitacion = {
  nombre: "apartamento en obra gris",
  ti: 8,
  tj: 7,
  pisoA: "#b4afa4",
  pisoB: "#aaa59a",
  paredIzq: "#9e988c",
  paredDer: "#b8b2a6",
  altoPared: 80,
  ventanas: [{ pared: "der", desde: 1.6, hasta: 4.6, z0: 18, z1: 66 }],
  muebles: [
    // escalera de obra
    { tipo: "cubo", i: 0.25, j: 0.4, wi: 0.18, wj: 0.18, alto: 42, mat: "metal" },
    { tipo: "cubo", i: 0.25, j: 1.0, wi: 0.18, wj: 0.18, alto: 42, mat: "metal" },
    { tipo: "cubo", i: 0.2, j: 0.4, wi: 0.3, wj: 0.8, alto: 2, mat: "metal", base: 14 },
    { tipo: "cubo", i: 0.2, j: 0.4, wi: 0.3, wj: 0.8, alto: 2, mat: "metal", base: 28 },
    { tipo: "cubo", i: 0.2, j: 0.4, wi: 0.3, wj: 0.8, alto: 2, mat: "metal", base: 41 },
    // tarros de pintura y baldosa apilada
    { tipo: "cubo", i: 0.3, j: 3.5, wi: 0.4, wj: 0.4, alto: 7, mat: "blanco" },
    { tipo: "cubo", i: 0.8, j: 5.6, wi: 0.35, wj: 0.35, alto: 6, mat: "vino" },
    { tipo: "cubo", i: 6.0, j: 0.25, wi: 0.9, wj: 0.7, alto: 9, mat: "piedra" },
    { tipo: "cubo", i: 6.05, j: 0.3, wi: 0.8, wj: 0.6, alto: 3, mat: "blanco", base: 9 },
    // cables colgando del techo, un cuadrito oscuro a media altura
    { tipo: "cubo", i: 2.6, j: 0.1, wi: 0.12, wj: 0.12, alto: 3, mat: "tinta", base: 58 },
  ],
};

/** Nicho: catálogo visual para e-commerce. Azotea al atardecer, exterior con horizonte. */
export const AZOTEA: Habitacion = {
  nombre: "azotea al atardecer",
  ti: 8,
  tj: 8,
  exterior: true,
  profundidadLosa: 14,
  pisoA: "#b9a894",
  pisoB: "#ad9c88",
  muebles: [
    // antepecho: dos muros bajos en el fondo
    { tipo: "cubo", i: -0.35, j: -0.35, wi: 0.35, wj: 8.7, alto: 16, mat: "piedra" },
    { tipo: "cubo", i: -0.35, j: -0.35, wi: 8.7, wj: 0.35, alto: 16, mat: "piedra" },
    // mesa de fotos con la caja de producto encima
    { tipo: "cubo", i: 2.5, j: 0.7, wi: 1.4, wj: 1.0, alto: 14, mat: "madera" },
    { tipo: "cubo", i: 2.75, j: 0.95, wi: 0.5, wj: 0.5, alto: 8, mat: "carton", base: 14 },
    { tipo: "cubo", i: 3.3, j: 1.0, wi: 0.35, wj: 0.35, alto: 5, mat: "vino", base: 14 },
    // torre de cajas sin fotografiar
    { tipo: "cubo", i: 5.6, j: 2.2, wi: 0.8, wj: 0.8, alto: 11, mat: "carton" },
    { tipo: "cubo", i: 5.65, j: 2.25, wi: 0.7, wj: 0.7, alto: 10, mat: "carton", base: 11 },
    { tipo: "cubo", i: 5.7, j: 2.3, wi: 0.6, wj: 0.6, alto: 9, mat: "carton", base: 21 },
    // aro de luz: trípode + aro
    { tipo: "cubo", i: 1.5, j: 1.6, wi: 0.14, wj: 0.14, alto: 30, mat: "tinta" },
    { tipo: "cubo", i: 1.25, j: 1.35, wi: 0.65, wj: 0.65, alto: 3, mat: "blanco", base: 30 },
    { tipo: "sprite", sprite: PERCHA, i: 0.8, j: 5.6 },
    { tipo: "sprite", sprite: ARBUSTO, i: 6.6, j: 6.2, sube: 2 },
  ],
};

export const ESCENARIOS = { TALLER, OBRA, AZOTEA, ARBOL, CLIENTE, SOCIO } as const;
