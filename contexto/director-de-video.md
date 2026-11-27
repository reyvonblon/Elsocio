# Director de video

Para cuando toca hacer un Reel, estudiar una referencia nueva o revisar un video antes de publicarlo.
El trabajo no es "poner texto con animación": es decidir **qué se ve en cada frase**.

## La regla que manda
**Lo que dice la voz es lo que se ve.** Si la frase dice "taller", la cámara está en un taller. Si dice
"pared", está en la pared. Si dice "audios", se ven los audios. Una frase sin un objeto que mostrar se
reescribe hasta que lo tenga. Fuente: análisis fotograma a fotograma de "Dos cafés",
`contexto/guia-estilo-video.md` §6.

## 1. Estudiar una referencia nueva (fotograma por fotograma)
1. Correr `bash redes/analizar_referencia.sh "<video>" [inicio] [duración]`. Si es una grabación de
   pantalla con varios reels, primero abrir `general.jpg` para ubicar dónde empieza cada uno y luego
   correrlo con el tramo de ese reel.
2. Abrir `densa.jpg` (2 fotogramas por segundo con el segundo marcado) y los `corte_*.jpg`.
3. Llenar esta tabla, una fila por cambio de frase:

   | Seg | Voz / texto | Qué se ve (sustantivos) | Cámara (se acerca, se aleja, paneo, entra) | Qué aparece encima (tooltip, tarjeta, brillo) |
   |---|---|---|---|---|

4. Sacar máximo 5 reglas de la tabla. Copiar **mecánica** (cómo se mueve, cómo se conecta la imagen
   con la voz), nunca colores, marcas, cifras ni promesas de la referencia (`guia-estilo-video.md` §4).
5. Si la referencia usa un escenario u objeto que el mundo no tiene (ej. una cocina, un carro de
   domicilios), anotarlo como pendiente para agregarlo en `redes/video-logo/src/mundo/` **antes** de
   escribir guiones que lo nombren.
6. Guardar la tabla y las reglas al final de `contexto/guia-estilo-video.md` como sección nueva
   (el cerebro de contenido lee ese archivo en cada pieza: así queda aprendido).

## 2. Escoger el formato
Hay tres, y El Socio los rota solo (nunca dos seguidos iguales, `guia-estilo-video.md` §12):
- **mundo**: contar un lugar (el taller, la obra, la tienda, la oficina). Ciudad isométrica + cámara.
- **collage**: explicar un proceso paso a paso (buscar clientes → correos → seguimiento → agenda).
  Recortes de papel, un objeto-metáfora por frase (`objeto` en cada plano), mascota El Socio.
- **duelo**: contraste directo frase por frase. Pantalla partida A arriba / B abajo con medidores.
Una referencia nueva que no encaje en ninguno se estudia con el paso 1 y se propone como formato nuevo
(ver §13 de la guía: "debate/mito" es el siguiente candidato).

## 3. Escribir un Reel (guion + storyboard)
1. **Gancho** con algo que se pierde: "Uno de estos dos talleres te va a arruinar la colección."
2. **Lado A** (2-3 bloques): el problema contado con objetos visibles (audios sueltos, cajas
   devueltas, pared rota, bandeja reventada).
3. **Lado B** (2-3 bloques): el mismo lugar resuelto (ficha en la pared, sala terminada, agenda llena).
4. **Cierre**: lo pone el código. "No seas el Taller A. Sé el Taller B. Con tu Socio, te lo solucionamos."
5. **Storyboard** en `planos`: un plano por frase (gancho, bloques, cierre), con `toma`, `lado`,
   `foco`, y en 2-3 planos un `tooltip` o una `tarjeta`. Vocabulario completo en
   `contexto/guia-estilo-video.md` §7. Nunca dos planos seguidos con la misma toma y el mismo foco.
6. Encolar: `python3 scripts/content_manager.py encolar --tipo video --gancho "..." --guion "bloque 1
   (salto de línea) bloque 2..." --nicho <nicho> --planos '<json>'` (y `--formato` solo si hay razón;
   vacío = rotación automática).

## 4. Revisar antes de aprobar (checklist)
Correr `bash redes/revisar_reel.sh redes/video-logo/out/<nombre>.mp4` y abrir `<nombre>_revision.jpg`.
- [ ] En cada frase, ¿se ve el objeto que nombra? Si no, cambiar el `foco` del plano y volver a generar.
- [ ] ¿Hay algún tramo con escena vacía o un cuarto con un solo objeto? No sale.
- [ ] "Tramos quietos de 3 s o más" tiene que dar 0.
- [ ] Gancho completo desde el primer fotograma.
- [ ] Cierre con la tarjeta de marca. Cero "link en bio", cero cifras, cero flechas o botones.
- [ ] Tooltips y tarjetas no tapan el objeto del que habla la frase.

## Prohibido
- Una escena genérica que no corresponde a la frase (el error de los reels viejos).
- Cifras de cualquier tipo en texto, tooltips o tarjetas.
- "Link en bio" o llamados de Facebook viejo dentro del video.
- Avatares de IA hablando o la cara de nadie.
