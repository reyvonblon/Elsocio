# Playbook de Estilo de Video — El Socio

Aprendizajes extraídos de las referencias en `contexto/referencias_video/` y adaptados a la identidad y pipeline técnico de El Socio (`Remotion` por frames PNG + `ffmpeg` vía `redes/generar_video.sh`).

---

## 1. Los 3 formatos de referencia que sí aplican a El Socio

1. **Diorama Paper-Cutout con Mascota (`@aldopaucaria` — "Harvey")** — *Prioridad #1 para explicar qué hace El Socio*
   - **Estructura visual:** 70% superior = escenario con muro de color/rayas verticales que cambia por escena; 30% inferior = suelo continuo (madera/superficie oscura) donde viven los subtítulos.
   - **Encabezado fijo arriba:** título corto en tarjeta tipo papel pegado con cinta (`TU PROBLEMA`, `LO QUE HACEMOS`, `CASO REAL`, etc.).
   - **Personaje recurrente:** usar el personaje SVG de `redes/avatar_personaje.html` (sombrero de copa, lentes, bigote, corbata roja) con micro-movimientos (rebote sutil, guiño, inclinación de sombrero) y accesorios según el caso (lupa, carpeta, plano, caja).
   - **Metáforas físicas en vez de texto largo:** imán, buzón, lupa sobre ficha, sello `"LISTO ✓"`, embudo o tarjeta `"RESUELTO"`.
   - **Transición:** wipe lateral continuo sobre la misma línea del suelo (la escena nueva entra de derecha a izquierda).

2. **Comparación A vs B Isométrica (`Dajent` / `Coffeefy`)** — *Ideal para casos de nicho o "antes vs después"*
   - **Hook de contraste:** dos negocios o dos personas iguales lado a lado (`"Dos talleres. Misma ciudad."`, `"Dos restaurantes. Misma cuadra."`).
   - **Dolor primero, solución después:** mostrar el caos manual (carpetas, errores, contador lento o local vacío) y cortar a la escena ordenada/iluminada con un sistema funcionando.
   - **Prueba visual sin audio:** cualquier persona en silencio debe entender qué pasa solo viendo las tarjetas, flechas, contadores y el cambio de estado (`Pendiente` → `Resuelto ✓`).

3. **Dark Tech UI / Bento Motion (`@aigencyx.labs` / `SYNC`)** — *Ideal para tips cortos, casos reales y series (`1/N`)*
   - **Fondo:** `#0a0a0a` (ya es la base de El Socio) con grilla sutil de puntos o líneas técnicas.
   - **Header persistente:** badge discreto arriba (`● CASO 01` o `EL SOCIO`) dentro de zona segura (`> 220px` desde arriba en `1080x1920`).
   - **Subtítulos cinéticos:** 1–3 palabras visibles a la vez o bloque corto con **resaltado de caja de color** (vino `#9c1c2e` / `#b22337` de la corbata o crema `#f5f0e6` con texto oscuro) en la palabra clave.
   - **Recursos programables 100% en Remotion:**
     - Comparación vertical dividida (arriba "Sin sistema / Solo" vs abajo "Con El Socio").
     - Desglose animado de conceptos o pasos (`1 → 2 → 3`).
     - Tarjetas de UI simuladas (mensaje recibido, propuesta, entregable listo, sello inclinado `"LEGAL"` / `"LISTO"`).
     - Cuadro de selección tipo editor alrededor de una palabra clave para enfatizarla.

---

## 2. Reglas de edición y ritmo aprendidas

- **Formato:** pasar de `1080x1350` a **`1080x1920` (9:16)** para Reels/Shorts, respetando zonas seguras (top `220px`, bottom `380px`, derecha `160px`).
- **Regla de los 2–3 segundos:** ningún plano queda estático más de `2.5s–3.0s`. Cada frase corta trae una micro-acción nueva (entra tarjeta, cambia fondo, aparece sello, sube contador, wipe lateral).
- **Hook sin calentamiento:** frame 1 arranca directo en el contraste o el problema (`"Dos talleres. El mismo error."`, `"Le pediste un ajuste. Llegó otro."`). Nunca empezar con el logo solo.
- **Un punto focal por escena:** título arriba, acción visual en el centro, subtítulo corto abajo. Cero párrafos largos.
- **Cierre seco + CTA claro:** terminar con la frase final + logo `El Socio` (`LogoSaludo`) y un CTA limpio (`"Cuéntanos tu problema · link en bio"` o `"Comenta..."`).
- **Capa sonora pendiente (las referencias estaban en silencio):** al montar el video final con `ffmpeg` o CapCut, sumar voz en off clara + SFX sutiles en cada aparición de tarjeta, sello, wipe y botón (`pop`, `whoosh`, `click`) + cama musical baja (`-18` a `-22 LUFS` debajo de la voz).

---

## 3. Qué NO copiar de las referencias

- **Estilos de IA generativa frame-a-frame (`10 Claude Animation styles`: Lego, CGI, PS2):** dependen de generar/renderizar imágenes externas pesadas y rompen la identidad sobria de El Socio.
- **Clips con cámara en mano (`Real Estate`)**: solo sirven si Raymond graba video real; para producción 100% automatizada en Mac, el camino es **vector/SVG + UI motion + personaje en Remotion**.
- **Colores neón genéricos (cian/amarillo gamer) como paleta principal:** adaptar siempre a la paleta de El Socio (`#0a0a0a`, `#ffffff`, vino `#9c1c2e` / `#b22337`, y crema/papel `#f5f0e6` cuando se use contraste cálido).
