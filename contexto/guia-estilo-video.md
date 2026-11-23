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
| cierre | Frase final + CTA de comentario. El CTA de `dajent.co` va en el pie de publicación ("Comenta TAG para probarlo"), no dentro del video. |

## 3. Reglas visuales y tipográficas

1. **9:16 vertical pleno.** Texto en la mitad superior, escena/acción en la inferior. Nunca texto sobre el centro de interés.
2. **Tipografía:** una sola sans-serif grotesca muy pesada (peso 700–900), tamaño enorme. **2–4 palabras por línea, máximo 2 líneas.** Cero párrafos.
3. **Una sola palabra resaltada por frase**, con caja de color sólido detrás y el resto en blanco o negro plano. Es el recurso más repetido de los 3 videos.
4. **Badge persistente arriba-izquierda** ("EP.2/50", "● CASO") y marca de agua discreta arriba-derecha.
5. **Dos fondos posibles, nunca foto detrás del texto:** casi negro con grilla de puntos sutil, o gris papel/off-white con grilla. Los 3 videos alternan entre estos dos y nada más.
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

## 5. Parámetros técnicos (Remotion en Mac Monterey)

- **Composición:** 1080x1920, **30 fps**. Hoy `LogoFrase` está en 1080x1350 y `LogoSaludo` en 1080x1080 (`redes/video-logo/src/Composition.tsx`): hay que crear la composición vertical.
- **Render:** `remotion render ... --sequence --image-format=png` + `ffmpeg` para unir. El render directo de Remotion exige macOS 15; esta ruta ya está probada y vive en `redes/generar_video.sh`.
- **Límite real del pipeline actual:** el patrón de `ffmpeg` es `element-%03d.png`, o sea **máximo 999 frames = 33.3 s a 30 fps**. Para videos más largos hay que pasar el patrón a `%04d`.
- **Duración objetivo:** 20–30 s → 600–900 frames. Cabe en el límite de arriba sin tocar nada.
- **Flags obligatorios en este Mac:** `--browser-executable` apuntando a Chrome, `--gl=swiftshader`, `--concurrency=1`.
- **Zonas seguras de Reels** (convención de la plataforma, no medida aquí): ~220 px arriba, ~380 px abajo, ~160 px a la derecha sobre 1080x1920.
- **Audio** (convención, no medido): si se suma voz o música, la cama va por debajo de la voz. Pendiente de validar contra material real con audio.
