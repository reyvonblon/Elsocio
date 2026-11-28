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

/** Manos al frente: se usa cuando el cliente trae algo. El objeto se estampa encima. */
const CLIENTE_CARGA: Record<number, string> = {
  16: "..AAaAAASSSSAAAaAA..",
  17: "..AAaAAASSSSAAAaAA..",
};

/** Desplaza un bloque de filas en horizontal. Sirve para negar con la cabeza sin redibujarla. */
const desplazarFilas = (lineas: string[], desde: number, hasta: number, dx: number): string[] => {
  if (dx === 0) return lineas;
  return lineas.map((l, i) => {
    if (i < desde || i > hasta) return l;
    return dx > 0 ? ".".repeat(dx) + l.slice(0, l.length - dx) : l.slice(-dx) + ".".repeat(-dx);
  });
};

export type Pose = "quieto" | "camina" | "carga" | "niega";

export type EstadoActor = { habla?: boolean; camina?: boolean; pose?: Pose; frame: number };

export const socioAnimado = ({ habla, pose = "quieto", frame }: EstadoActor): Sprite => {
  let lineas = SOCIO.lineas;
  // ciclo de boca ~4 veces por segundo, como la mascota del collage y como MOKO
  if (habla && frame % 8 < 4) lineas = cambiar(lineas, SOCIO_BOCA_ABIERTA);
  if (pose === "camina") lineas = cambiar(lineas, frame % 16 < 8 ? SOCIO_PASO_A : SOCIO_PASO_B);
  // negar: la cabeza (filas 0-20) se mueve sola, el cuerpo se queda. Es el gesto que
  // convierte "está ahí parado" en "está reaccionando a lo que ve".
  if (pose === "niega") {
    const fase = Math.sin(frame * 0.33);
    lineas = desplazarFilas(lineas, 0, 20, fase > 0.4 ? 1 : fase < -0.4 ? -1 : 0);
  }
  return lineas === SOCIO.lineas ? SOCIO : { paleta: SOCIO.paleta, lineas };
};

export const clienteAnimado = ({ habla, pose = "quieto", frame }: EstadoActor): Sprite => {
  let lineas = CLIENTE.lineas;
  if (habla && frame % 8 < 4) lineas = cambiar(lineas, CLIENTE_BOCA_ABIERTA);
  if (pose === "carga") lineas = cambiar(lineas, CLIENTE_CARGA);
  if (pose === "camina") {
    lineas = cambiar(lineas, frame % 16 < 8
      ? { 26: "....JJJJ..JJJJ......", 27: "...JJJJ....JJJJ.....", 28: "...JJJJ....JJJJ.....", 31: "...KKKKK..KKKKK.....", 32: "..KKKKK....KKKKK....", 33: "..KKKKK....KKKKK...." }
      : { 26: ".....JJJJJJJJ.......", 27: ".....JJJJJJJJ.......", 28: ".....JJJJJJJJ.......", 31: "....KKKKKKKKKK......", 32: "....KKKKKKKKKK......", 33: "....KKKKKKKKKK......" });
  }
  return lineas === CLIENTE.lineas ? CLIENTE : { paleta: CLIENTE.paleta, lineas };
};

/**
 * Respiración y balanceo: desfasados a propósito. Si todo oscila al mismo compás el muñeco se
 * ve de cuerda (§15.1). Devuelve cuántos píxeles sube el sprite en este fotograma.
 */
export const respiracion = (frame: number, desfase = 0): number =>
  Math.sin((frame + desfase) * 0.17) > 0.55 ? 1 : 0;
