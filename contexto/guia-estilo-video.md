# Guía de estilo de video — El Socio

Destilada de los 3 archivos de `contexto/referencias_video/` midiéndolos con `ffprobe`/`ffmpeg` e
inspeccionando 20 fotogramas clave. Reemplaza a `redes/ESTILO_VIDEO.md` como fuente única.

**Qué son las referencias (dato medido, no suposición):** no son 3 reels sueltos. Son 3 grabaciones
de pantalla de Instagram, de 1:46, 3:54 y 5:34, donde se recorren varios reels ajenos seguidos. Por eso
se ve la interfaz de IG (botón "Me gusta", contador de comentarios, panel de comentarios).
Cuentas visibles: `@aldopaucaria`, `@aigencyx.labs`, `dajent.co`, "Método Atómico", y una colección
guardada llamada "Videos Claude".

| | Video 1 | Video 2 | Video 3 |
|---|---|---|---|
| Resolución | 384x600 | 350x600 | 350x600 |
| Duración | 234.45 s | 106.27 s | 334.17 s |
| FPS (nominal / real) | 60 / 55.5 | 60 / 57.4 | 60 / 45.2 |
| Códec | h264 yuv420p | h264 yuv420p | h264 yuv420p |
| **Audio** | **ninguno** | **ninguno** | **ninguno** |

> **Advertencia sobre el audio:** los 3 archivos **no tienen pista de audio** (se grabaron con el
> altavoz silenciado; el icono de mute es visible en casi todos los fotogramas). Cualquier regla sobre
> voz en off, música o SFX en este documento es **convención de la plataforma, no algo medido aquí**, y
> está marcada como tal. Nada de lo que sigue permite afirmar cómo suenan esos reels.

---

## 1. Ritmo (medido con detección de escena)

- **Un corte o cambio de plano cada ~2 segundos.** Medido en el tramo 40–70 s del video 2: cortes en
  44.7, 50.1, 52.3, 54.4, 56.6, 58.6, 60.9, 62.9, 66.1, 67.2 y 69.3 s → intervalo medio **2.1 s**,
  mínimo 1.1 s, máximo 3.2 s (ese 3.2 es el plano más lento de todo el tramo).
- **Dentro de cada plano hay una ráfaga de micro-cambios de 0.03–0.12 s que dura 0.3–0.6 s.** Esa es la
  animación de entrada del texto: la frase no aparece de golpe, entra palabra por palabra en medio segundo.
- **Los cortes duros son raros.** Con umbral alto (scene > 0.4) solo salen 12–13 por video, y aparecen
  agrupados: marcan el cambio de un reel a otro o de un bloque narrativo a otro, no el ritmo interno.
- **Traducción para El Socio:** a 30 fps, **cambio visual cada 60 frames** y **entrada de texto en 9–18
  frames**. Ningún plano estático más de 90 frames (3 s).

## 2. Estructura de guion (la que repiten los 3)

El esqueleto dominante es **A vs B**, literal: "Dos DJs", "Dos cafés. Misma cuadra", "ASÍ LO HACÍA /
ASÍ LO HACE AHORA", "NOVATO vs PRO", "TU MOTION 2D / PASADO A 3D".

| Tiempo | Qué pasa |
|---|---|
| 0.0–2.0 s | **Gancho sin calentamiento.** Texto grande ya presente en el frame 1. Es una afirmación de contraste o una negación provocadora ("AI can't edit real estate videos"), nunca el logo solo. |
| 2–6 s | Se plantan los dos lados del contraste, idénticos salvo una diferencia. |
| 6–18 s | Desarrollo numerado y explícito: "TRES:", "1 CONECTAR · 2 ANALIZAR · 3 NAVEGAR", "01…10". Un paso por plano. |
| 18–25 s | El estado cambia a la vista: etiqueta flotante, contador, sello, marca de verificación. |
| cierre | Cierre de venta en golpes: "No seas el Taller A. Sé el Taller B." + tarjeta de marca "Con tu Socio, te lo solucionamos." (ver §8). Nada de CTA de comentario ni "link en bio" dentro del video. |

## 3. Reglas visuales y tipográficas

1. **9:16 vertical pleno.** Texto en la mitad superior, escena/acción en la inferior. Nunca texto sobre el centro de interés.
2. **Tipografía:** una sola sans-serif grotesca muy pesada (peso 700–900), tamaño enorme. **2–4 palabras por línea, máximo 2 líneas.** Cero párrafos.
3. **El resalte sigue la voz, no se queda quieto** (corregido el 2026-11-26). La caja vino va sobre la palabra que se está diciendo en ese instante y salta a la siguiente: una sola caja a la vez, viajando por toda la frase. Dejarla clavada en una sola palabra durante los 4 s del plano se ve como una imagen fija y fue el error que Raymond frenó. Lo implementa `Titular` + `tiemposPalabras` en `comun.tsx`: el reparto es por largo de palabra dentro del tramo real de voz (`tiemposBloques`), así no hace falta transcripción. **Los tres formatos lo usan** (mundo y duelo vía `Titular`, collage vía su `Karaoke`). Toda palabra lleva el mismo relleno y solo cambia el color del fondo, para que el texto no se reacomode cuando la caja salta.
4. **Badge persistente arriba-izquierda** ("EP.2/50", "● CASO") y marca de agua discreta arriba-derecha.
5. **Un solo mundo, nunca un fondo vacío.** (Corregido el 2026-11-24 tras analizar "Dos cafés" fotograma por fotograma.) Arriba va una banda crema con el texto que se funde con la escena; abajo, SIEMPRE un lugar lleno de cosas. El motor viejo alternaba fondo negro/crema con 4 escenas genéricas y por eso salían "3 cuadros sin nada": eso queda descartado (ver §6).
6. **Escenas isométricas vectoriales con etiquetas flotantes tipo tooltip:** "4,128 TRACKS", "Café 2", "Martina siempre pide Latte y 2 medialunas". El dato concreto va en la etiqueta, no en el locutor.
7. **Subtítulo quemado abajo**, 2–3 palabras, con una resaltada: "MUEVE LA LUZ", "TUS MOTION".
8. **Paleta de El Socio** (sustituye a la de las referencias): fondo `#0a0a0a`, texto `#ffffff`, resalte vino `#9c1c2e` / `#b22337`, fondo claro alterno crema `#f5f0e6`. Las referencias usan cian eléctrico, naranja y dorado: **no se copian.**

## 4. Qué NO copiar

- **Cualquier cifra.** Los videos exhiben números todo el tiempo ("−40 CRÉDITOS", "4,128 TRACKS", "50%"). El Socio no dice cifras: ni precios, ni plazos, ni resultados (`identidad.md`, regla 1). Un dato de ejemplo dentro de una escena inventada igual se lee como promesa: no va.
- **Vender la herramienta en vez del resultado.** Dos de los tres videos ponen la interfaz de Claude en pantalla como protagonista ("CLAUDE DID THIS"). El Socio vende que el problema queda resuelto, no con qué se resolvió.
- **Promesas de viralidad y lenguaje de hype** ("10 Claude Animation styles To Go Viral"). Choca de frente con la voz sobria.
- **Estética gamer/neón** del video 3: barras de vida, moneda "VS" dorada, cian eléctrico, HUD de videojuego.
- **PiP de la cara del creador hablando** (video 3). Solo tiene sentido si Raymond decide grabarse; mientras no, el camino es 100% vectorial.
- **Estilos generativos frame a frame** (Lego, pixel art, CGI): rompen la identidad y obligan a generar imágenes pesadas.
- **"Link en bio", flechas o botones dentro del video.** Se ve como video viejo de Facebook. El link vive en el pie de publicación; el video cierra con la tarjeta de marca (§8).

## 5. Parámetros técnicos (Remotion en Mac Monterey)

- **Composición:** 1080x1920, **30 fps**. Los Reels salen con **`ReelMundo`** (`redes/video-logo/src/ReelMundo.tsx` + carpeta `mundo/`). `ReelVertical` queda solo como respaldo (`REEL_MOTOR=ReelVertical`).
- **Render:** `remotion render ... --sequence --image-format=png` + `ffmpeg` para unir. El render directo de Remotion exige macOS 15; esta ruta ya está probada y vive en `redes/generar_video.sh`.
- **Límite real del pipeline actual:** el patrón de `ffmpeg` es `element-%03d.png`, o sea **máximo 999 frames = 33.3 s a 30 fps**. Para videos más largos hay que pasar el patrón a `%04d`.
- **Duración objetivo:** 20–30 s → 600–900 frames. Cabe en el límite de arriba sin tocar nada.
- **Flags obligatorios en este Mac:** `--browser-executable` apuntando a Chrome, `--gl=swiftshader`, `--concurrency=1`.
- **Zonas seguras de Reels** (convención de la plataforma, no medida aquí): ~220 px arriba, ~380 px abajo, ~160 px a la derecha sobre 1080x1920.
- **Audio** (convención, no medido): si se suma voz o música, la cama va por debajo de la voz. Pendiente de validar contra material real con audio.


---

## 6. Lección fotograma a fotograma: "Dos cafés" (Coffeefy) — la referencia que manda

Analizada con `redes/analizar_referencia.sh` sobre el video 2, tramo 30–60 s, a 2 fotogramas por segundo.
Es la referencia a copiar en **mecánica** (no en colores ni en marca).

| Seg | Voz / texto | Qué se ve | Cámara |
|---|---|---|---|
| 0.0 | "Dos cafés. Misma cuadra." | La cuadra entera desde arriba, píldoras "Café 1" y "Café 2" | plano general, quieta |
| 2.0 | "Dos cafés." | Fachada del Café 1 con toldo, gente en la acera | baja y se acerca al Café 1 |
| 9.0 | "Buen café. Buenos precios." | Los dos cafés en la misma toma | se abre para mostrar ambos |
| 14.7 | "Solo uno está siempre lleno." | El Café 2 se ilumina (brillo cálido) | se desliza hacia el Café 2 |
| 17.2 | "¿Por qué?" | Café 2 sigue iluminado | casi quieta (pausa dramática) |
| 20.2 | "Tiene un sistema." | El techo desaparece: se ve el interior lleno de gente | entra al local |
| 22.3 | "QR en la mesa → sellos → premio" | Barra y mesa con el QR; el texto se arma con flechas | zoom a la barra |
| 26.6 | "Recuerda lo que piden." | Tooltip sobre una clienta: "Martina siempre pide Latte y 2 medialunas" | paneo a las mesas |
| 28.6 | "Te avisa quién dejó de venir." | Tarjeta de interfaz flotante sobre la escena | quieta, la tarjeta entra |

**Las 5 reglas que salen de ahí (y que el motor ya aplica en código):**
1. **Un mundo continuo.** Toda la historia pasa en la misma cuadra. Nunca se corta a un fondo vacío.
2. **La cámara viaja en vez de cortar.** ciudad → calle → entra al local (el techo se desvanece) → detalle. Para pasar del local A al B, se aleja a la calle y vuelve a entrar.
3. **Cada frase tiene su toma y muestra el sustantivo exacto que dice la voz.** Si la voz dice "taller", se ve un taller; si dice "pared", la cámara está en la pared; si dice "audios", se ven los audios. Este es el error que tenían los reels viejos ("habla de taller y muestra una sala").
4. **Escenas llenas de detalle**: personas, carros moviéndose, árboles, muebles, herramientas, papeles. Un cuarto con un solo objeto no es una escena.
5. **El dato va en un tooltip o una tarjeta de UI** encima del objeto, no en un párrafo.

## 7. Storyboard (`planos`): cómo se le dice al motor qué mostrar

Cada Reel lleva un plano por frase, en orden: gancho, cada bloque, y el cierre. Campos (todos opcionales:
si falta uno, `ReelMundo` lo deduce de las palabras de la frase):

- `toma`: `ciudad` (los dos locales de lejos) · `pareja` (los dos, más cerca) · `calle` (fachada de uno) · `local` (adentro) · `detalle` (zoom a un objeto)
- `lado`: `A` = el negocio sin sistema (caos) · `B` = el negocio con El Socio (orden)
- `foco` (objeto exacto, por nicho):
  - **taller** (confección): mesa, ficha, audios, maquinas, perchero, maniqui, lote, persona, pared
  - **obra** (remodelación/espacios): pared, andamio, plano, sala, sofa, ventana, cables, persona
  - **estudio** (catálogo/e-commerce): inventario, producto, luces, celular, camara, pantalla, ropa, persona
  - **oficina** (agencias/automatización): escritorio, pantalla, agenda, telefono, papeles, persona
- `estado`: `caos` u `orden` (por defecto A=caos, B=orden)
- `tooltip`: etiqueta flotante, máx 26 caracteres, cero cifras. En 2 o 3 planos, no en todos.
- `tarjeta`: `correo`, `agenda`, `ficha`, `catalogo`, `render`, `chat` (audios sueltos). Máx 2 por reel.

**Escribe frases con objetos que se puedan mostrar** ("audios sueltos", "la ficha", "la pared", "las cajas sin foto", "la bandeja", "la agenda"). Una frase abstracta ("optimizamos tus procesos") no tiene qué mostrar y deja la cámara sin destino.

## 8. Gancho y cierre (aprobado por Raymond, 2026-11-24)

- **Gancho:** tensión en el primer segundo con algo que se pierde: "Uno de estos dos talleres te va a arruinar la colección." El texto está COMPLETO desde el fotograma 1 y la cámara cae en picada sobre la cuadra en 0.7 s.
- **Cierre de venta, no despedida:** "No seas el Taller A. Sé el Taller B. Con tu Socio, te lo solucionamos." Cada oración es un golpe con su toma (A apagado → B iluminado) y la última es la **tarjeta de marca**: fondo crema, sombrero + gafas, "El Socio" y la línea de venta. Lo arma el código (`content_manager.cierre_de_venta`) según el nicho: Taller / Local / Tienda / Agencia.
- **Prohibido dentro del video:** "link en bio", "comenta", flechas, botones. Elegante o nada.

## 9. Cómo aprender de una referencia nueva

Ver `contexto/director-de-video.md`. Resumen: `redes/analizar_referencia.sh` → leer las
hojas de contacto → llenar la tabla de §6 para la referencia nueva → sacar reglas → si piden un objeto o
escenario que el mundo no tiene, se agrega en `redes/video-logo/src/mundo/` antes de usarlo en un guion.

---

## 10. Formato "collage" — aprendido de "Harvey, un vendedor con IA" (video 1, 66–120 s)

| Seg | Voz / subtítulo | Qué se ve | Movimiento |
|---|---|---|---|
| 0–3 | "Un vendedor con IA te trae clientes" | Rótulo de cinta arriba; papelitos-correo volando alrededor de la mascota | papeles caen y rebotan |
| 3–6 | "tiene una función: traerte más clientes" | Un imán gigante; personitas recortadas vuelan hacia él | el imán entra con rebote |
| 6–9 | "Se llama Harvey y es gratis" | Etiqueta "HOLA ME LLAMO" que se escribe letra por letra | pared cambia a rosa |
| 9–13 | "Le decís qué vendés y a quién" | Diana con flecha que se clava | pared azul |
| 13–18 | "Encuentra leads, investiga cada uno" | Pecera con personitas y un anzuelo que saca una | pared verde agua; contador sube |
| 18–22 | "Separa los que mejor encajan" | Máquina con luces "ENCAJAN" | pared mostaza |
| 22–28 | "Escribe e-mails personalizados" | Tostadora que bota sobres | pared roja |
| 28–33 | "Hace seguimiento de las respuestas" | Embudo sobre una parrilla: LEADS → CHARLAS | pared mostaza |
| 33–36 | "Trabaja hasta agendarte las reuniones" | Agenda "VACÍA" → "LLENA", apretón de manos | pared morada |
| 36–42 | "Todo solo, en tu computadora / panel en vivo" | Pantalla con embudo de barras de colores, "EN VIVO" | fondo azul noche con circuitos |

**Reglas que salen de ahí:**
1. **Cada paso cambia el color de la pared** (rayas verticales). La composición se repite, el color hace el corte.
2. **Un objeto-metáfora por paso, grande y recortado en papel** (borde blanco + sombra dura). El objeto ES lo que dice la voz.
3. **Rótulo de cinta arriba** con el nombre del paso y **contador pequeño** que avanza (aquí sin números: puntos que se llenan).
4. **Mascota pequeña** que reacciona: en El Socio es El Socio mismo (sombrero + gafas), triste en el lado A, feliz en el B.
5. **Subtítulo karaoke abajo**: 2-3 palabras en papelitos, la que suena en vino.
6. Ideal para **explicar un proceso paso a paso** — justo la oferta ancla (buscar clientes → correos → seguimiento → agenda).

## 11. Formato "duelo" — aprendido de "Novato vs Pro" (video 3, 36–96 s)

| Seg | Voz | Arriba (NOVATO) | Abajo (PRO) |
|---|---|---|---|
| 0–4 | "Mismo tema. Mismas ganas." | ventana con el mismo tema | ventana con el mismo tema |
| 4–15 | "El novato abre… pide la escena… otra vez" | contador de créditos bajando en rojo | apagado, esperando con "..." |
| 15–25 | "Claude, conectado a su carpeta… escribe… con código" | apagado | la ventana se llena, luna = trabaja de noche |
| 25–35 | "El novato publica… y se acabó" | teléfono con un video, visitas quietas | multiplica versiones |
| 35–50 | "No contesta a nadie" vs "le llega su enlace solo" | comentarios sin responder | comentarios activados, enlaces que salen solos |
| 50–58 | "Mismo tema" | reloj, ventas en cero | reloj, venta nueva |

**Reglas:**
1. **Pantalla partida horizontal** con línea brillante y **moneda VS** en el centro.
2. **Cada frase actualiza SOLO su mitad**; la otra se apaga para que el ojo sepa dónde mirar.
3. Cada mitad = **ventana de app** (qué pasa) + **medidor grande** (cómo va). En El Socio el medidor es un anillo que se vacía (A) o se llena (B), **nunca un número**.
4. El lado B espera vacío con "..." hasta que le toca: eso crea la tensión.
5. En el cierre: sello **"NO"** sobre A y **"SÍ"** sobre B, luego la tarjeta de marca.

## 12. Rotación de formatos (regla de código)

`content_manager.elegir_formato()` garantiza que **nunca salen dos reels seguidos con el mismo formato** y
que en cada vuelta se usen los tres (mundo, collage, duelo). El cerebro sugiere el que mejor cuente la idea;
si repite el anterior, el código lo cambia por el menos usado. La voz, la sincronía y el cierre de venta son
los mismos en los tres.

## 13. Referencias estudiadas pero todavía sin formato propio

- **"¿Sync es trampa?" (video 1, ~170–230 s):** formato *debate/mito*. Un objeto protagonista enorme (el botón SYNC)
  con sello "¿TRAMPA?", y luego argumentos "EN CONTRA" / "A FAVOR" con íconos (oído vs perilla). Sirve para
  "¿Automatizar tus ventas es trampa?". Candidato a cuarto formato.
- **"EP.2/50 Máster de Claude" (video 1, ~118–160 s):** formato *serie explicativa*: badge de episodio, agenda
  numerada de lo que se va a ver, íconos que aparecen con su etiqueta. Útil si El Socio arranca una serie.
- **"Dos DJs" (video 2, 0–30 s):** el mismo mecanismo de mundo isométrico pero de noche (fondo azul oscuro,
  pantallas que brillan) con la app real en primer plano. Variante nocturna posible del formato mundo.
- **Descartados** (por la guía §4): "10 Claude animation styles", estilos generativos (Lego, Pixar, GTA),
  monos con IA, lluvia de monedas, avatares y caras.

---

## §14 Render real en el Mac (medido el 2026-11-24, no estimado)

Los tres formatos se renderizaron de verdad en este Mac (Intel, macOS Monterey 12.7, Chrome +
swiftshader, `--concurrency=1`) con voz neuronal. Lo que se aprendió, para no repetirlo:

### Tiempos reales de un reel de 27,5 s (825 fotogramas, 1080x1920 @ 30 fps)

| Formato | Antes | Después de optimizar | Qué lo hacía lento |
|---|---|---|---|
| mundo | 15:12 | ~14:15 | recortaba la ciudad con 420 px de margen y dibujaba edificios enteros, ventana por ventana, fuera de cámara |
| collage | 18:39 | ~13:30 | dos `filter: drop-shadow` por fotograma (el 36 % del tiempo: swiftshader no tiene GPU) |
| duelo | 13:07 | ~13:00 | ya estaba bien |

La voz tarda ~45 s aparte (Edge neural por WebSocket) y el `ffmpeg` final, segundos.
**Regla: un reel cuesta entre 13 y 15 minutos de Mac.** No se pueden encolar cinco reels seguidos
esperando que acaben rápido; `TIMEOUT_RENDER` está en 1800 s por eso.

**Sombras sin filtro.** Una sombra dura (sin desenfoque) nunca va con `filter: drop-shadow`: se dibuja
el mismo grupo dos veces, la copia de abajo desplazada y en negro (`ReelCollage.CSS_SOMBRA_PAPEL`,
una regla CSS gana sobre los atributos `fill` de cada forma). Se ve idéntico y cuesta un tercio menos.

**Recorte de la ciudad.** `visibleMedio` = media pantalla + 260 px (lo que mide el objeto más ancho,
un edificio ≈ 173 px en isométrico). Con 420 no se notaba nada en pantalla y se pagaba en cada frame.

### Para iterar sin esperar 15 minutos
```bash
cd redes/video-logo && npx remotion still Reel salida.png --frame=N --props=props.json \
  --browser-executable="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --gl=swiftshader
```
Tarda ~25 s y sirve para revisar un encuadre o el subtítulo. **El `--browser-executable` no es opcional en este Mac:** el Chrome que trae Remotion no arranca en Monterey (falla con `SIGABRT` en VideoToolbox). El video completo solo al final.

### Fuentes
**"Playfair Display" no está instalada en este Mac** y no se carga de ninguna parte: el render cae a
**Georgia**, que sí existe (`/System/Library/Fonts/Supplemental/Georgia.ttf`) y se ve elegante en la
tarjeta de marca. La cascada se deja como está por si algún día se instala. El sans (`-apple-system`)
resuelve a SF Pro sin problema.

### Red
El TTS neuronal necesita salida a `speech.platform.bing.com` por WebSocket TLS. Si la red está
bloqueada, `generar_video.sh` cae solo a una pista de diseño sonoro sin voz y avisa por `stderr`:
el video igual sale, pero mudo. Si el reel sale sin voz, el problema es la red, no el motor.

### Lo que el primer render destapó (y ya está corregido en código)

| Se veía | Por qué | Arreglo |
|---|---|---|
| "El patronista adivina medidas" con una ficha exacta y el rótulo "FICHA EXACTA" | el mapeo palabra→objeto no miraba el lado | `EQUIVALENTE_EN_CAOS` en `ReelCollage`: en el lado A, ficha→papeles, agenda→reloj, pantalla→papeles |
| "Las máquinas cosen" mostrando una ficha | `duelo` no tenía panel de máquina y caía en `/adivina/` | panel `maquina` nuevo + su regla, antes que las demás |
| 3,5 s de arranque congelado en `duelo` | el gancho esperaba con las dos ventanas vacías ("...") | en el gancho las dos mitades reciben el MISMO encargo, escalonado a lo largo de toda la frase |
| "No seas el Taller A" mostrando un techo con una píldora | el cierre usaba toma `calle` | el cierre usa toma `local`: se ve el taller A en caos y el B en orden |
| medio segundo largo del local equivocado al cambiar de lado | transición de 1,05 s | 0,78 s (`trans` en `camaraEn`) |
| los dos locales diminutos y pegados al titular en el gancho | `ciudad` con zoom 0,74 y cámara a z=40 | zoom 0,9 y z=118: la cuadra baja al centro del encuadre |

### Cifras: la última puerta
La guarda de ventas deja pasar plazos ("sale en 15 días") a propósito, porque en un correo son
normales. En un video NO: §4 prohíbe toda cifra. `content_manager._cifras_en_pantalla()` bloquea
ahora cualquier dígito en gancho, guion, caption, etiquetas y tooltips de una pieza. La misma idea en
letras ("en quince días") sí pasa: lo prohibido es el dígito en pantalla, no la idea.

---

## §15 Referencia "MADE IN CHINA" (MOKO) — la que pidió Raymond el 2026-11-26

Archivo: `contexto/referencias_video/moko_made_in_china.mov` (45,4 s · 1104x1908 · 60 fps).
Hojas de contacto del análisis en `contexto/referencias_video/moko_analisis/`.

### Lo que NO se puede copiar (y por qué)
Es animación de personajes 2D dibujados, con expresión facial, labios sincronizados y cámara de cine.
El motor de El Socio es SVG isométrico vectorial: no dibuja caras ni actúa personajes. Intentar
imitar el **estilo** sería pelear contra el material. Se copia la **mecánica** (guía §4).

### Medición (mismo indicador que usamos en los reels propios)
| | Micro-movimiento (scene > 0,1) | Cortes duros (scene > 0,25) |
|---|---|---|
| MOKO | **76 por 30 s** | **1 por 30 s** |
| Referencia vieja (video 2) | 87 por 30 s | 10 por 30 s |
| `content_0005` (mundo) | **2 por 30 s** | 2 por 30 s |

**El hallazgo que corrige §1:** esta referencia es la que Raymond llama "fluida y limpia", y casi no
tiene cortes (1 cada 30 s). La fluidez NO viene de cortar más. Viene de que **nada está quieto nunca**
entre corte y corte. El §1 pedía "un corte cada 2 s" leyendo otra referencia; para el efecto que
Raymond quiere, lo que manda es el movimiento continuo, no la frecuencia de corte.

### Las 5 reglas que sí se copian
1. **La cámara no se detiene jamás.** En los 6 s analizados fotograma a fotograma no hay un solo plano
   fijo: siempre hay paneo o acercamiento lento. Un plano quieto es un plano muerto.
2. **Un sujeto grande por plano.** El protagonista ocupa 50-70% del alto del cuadro. Nunca una vista
   general donde todo es pequeño. En isométrico: acercarse al objeto que nombra la voz, no mostrar
   la escena entera desde lejos.
3. **Profundidad por capas.** Siempre hay algo en primer plano (botellas, platos) delante del sujeto,
   y fondo oscuro detrás. El Socio dibuja todo en un plano único: falta ese delante/detrás.
4. **Paleta oscura con acentos saturados.** Fondo nocturno + un rojo o azul fuerte en el punto de
   interés. El Socio hoy es beige sobre beige: en el feed se pierde.
5. **Subtítulo discreto.** Dos o tres palabras pequeñas abajo, blancas, sin caja. No compite con la
   imagen. (El karaoke grande actual ocupa el triple.)

### Pendiente antes de escribir guiones que lo usen
Las reglas 3 y 4 necesitan trabajo en `mundo/`: hoy no existe capa de primer plano ni variante
nocturna de las escenas.

### §15.1 Cómo anima MOKO a los personajes (medido a 10 fps sobre el tramo 7,5-9,5 s)

Hoja de contacto: `contexto/referencias_video/moko_analisis/personaje.jpg`.

| Qué se mueve | Cada cuánto | Lo que teníamos |
|---|---|---|
| **La boca, al hablar** | abre/cierra cada 2-3 fotogramas | boca dibujada como path FIJO: la misma mueca 27 s |
| Cabeza: gira e inclina | continuo, nunca fija | cabeza clavada al torso |
| Hombros y torso | continuo | torso rígido |
| Manos: gesticulan, suben a la cara | por frase | `Persona` solo tenía brazos si `brazosArriba` |
| Piernas | al caminar | existía `paso`, pero NINGUNA llamada se lo pasaba |

**La regla:** un personaje vivo mueve el cuerpo ENTERO todo el rato, no una parte. Y cada eje va a su
propia frecuencia con su desfase — si todo oscila al mismo compás se ve como un muñeco de cuerda.

**Lo más barato y lo que más rinde: la boca.** Es lo que más hace que un dibujo parezca vivo. En
`Mascota` (collage) ya está: un ciclo cada 7 frames (~4 veces por segundo).

**Techo conocido:** en el formato `mundo` las personas miden ~65 px de alto con el zoom máximo.
Animarlas mejora, pero no se percibe como en MOKO, donde el personaje ocupa 50-70% del cuadro
(regla 2 de §15). Para acercarse de verdad al efecto haría falta un personaje grande en primer
plano, que hoy solo existe en `collage` (la mascota) y no en `mundo`.
