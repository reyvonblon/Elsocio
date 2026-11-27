/**
 * Animación de los sprites.
 *
 * Regla de §15.1 (medida sobre MOKO): un personaje vivo mueve el cuerpo ENTERO todo el rato, y
 * cada eje va a su propia frecuencia. Lo más barato y lo que más rinde es la boca.
 *
 * Aquí eso cuesta casi nada: un sprite es una lista de cadenas, así que "abrir la boca" es
 * cambiar UNA fila. En SVG eso era redibujar un path.
 */

import type { Sprite } from "./lienzo";
import { CLIENTE, SOCIO } from "./sprites";

const cambiar = (lineas: string[], cambios: Record<number, string>): string[] =>
  lineas.map((l, i) => cambios[i] ?? l);

/** El Socio no tiene boca: el que habla es el mostacho, y debajo se abre el hueco. */
const SOCIO_BOCA_ABIERTA: Record<number, string> = {
  16: "......KKKKKKKKKKKK......",
  17: "......SSSKKKKKKSSS......",
};

const SOCIO_PASO_A: Record<number, string> = {
  36: "......KKKK....KKKK......",
  37: "......KKKK....KKKK......",
  38: "......KKKK....KKKK......",
  39: "......KKKK....KKKK......",
  40: "......KKKK....KKKK......",
  41: ".....nKKKK....KKKKn.....",
  42: ".....KKKKK....KKKKK.....",
  43: ".....KKKKK....KKKKK.....",
};

const SOCIO_PASO_B: Record<number, string> = {
  36: ".......KKKKKKKKKK.......",
  37: ".......KKKKKKKKKK.......",
  38: ".......KKKKKKKKKK.......",
  39: ".......KKKKKKKKKK.......",
  40: ".......KKKKKKKKKK.......",
  41: "......nKKKKKKKKKKn......",
  42: "......KKKKKKKKKKKK......",
  43: "......KKKKKKKKKKKK......",
};

const CLIENTE_BOCA_ABIERTA: Record<number, string> = { 6: "....SSSSKKKKSSSS...." };

export type EstadoActor = { habla?: boolean; camina?: boolean; frame: number };

export const socioAnimado = ({ habla, camina, frame }: EstadoActor): Sprite => {
  let lineas = SOCIO.lineas;
  // ciclo de boca ~4 veces por segundo, como la mascota del collage y como MOKO
  if (habla && frame % 8 < 4) lineas = cambiar(lineas, SOCIO_BOCA_ABIERTA);
  if (camina) lineas = cambiar(lineas, frame % 16 < 8 ? SOCIO_PASO_A : SOCIO_PASO_B);
  return lineas === SOCIO.lineas ? SOCIO : { paleta: SOCIO.paleta, lineas };
};

export const clienteAnimado = ({ habla, frame }: EstadoActor): Sprite => {
  if (!habla || frame % 8 >= 4) return CLIENTE;
  return { paleta: CLIENTE.paleta, lineas: cambiar(CLIENTE.lineas, CLIENTE_BOCA_ABIERTA) };
};

/**
 * Respiración y balanceo: desfasados a propósito. Si todo oscila al mismo compás el muñeco se
 * ve de cuerda (§15.1). Devuelve cuántos píxeles sube el sprite en este fotograma.
 */
export const respiracion = (frame: number, desfase = 0): number =>
  Math.sin((frame + desfase) * 0.17) > 0.55 ? 1 : 0;
