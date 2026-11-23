# Plan de contenido — unificar `redes/` con El Socio

Hoy `redes/` es un taller suelto: frases a mano, PNG generados con Chrome headless, un Remotion
que renderiza 1080x1350 y publicación 100% manual. No habla con el motor de ventas
(`sales_agent.py`, `autopilot_dispatcher.py`, `data/el_socio.db`). Estos 3 pasos lo conectan.

---

## Paso 1 — Guía destilada y Git blindado ✅ hecho

- `.gitignore` cerrado a multimedia pesada: `.mov`, `.mp4`, `redes/posts/*.png`, `redes/voz/*.aiff`,
  `redes/voz/*.m4a`, `redes/video-logo/out/`. Verificado con `git status`: nada pesado entra al repo.
- Los 3 videos de referencia medidos con `ffprobe`/`ffmpeg` (resolución, duración, fps, audio, cortes)
  y 20 fotogramas clave inspeccionados → `contexto/guia-estilo-video.md`.
- Hallazgo que condiciona todo lo demás: **las referencias no tienen pista de audio**. Lo que se puede
  copiar con certeza es el ritmo visual y la estructura de guion, no el tratamiento sonoro.
- `redes/ESTILO_VIDEO.md` queda duplicado con la guía nueva. Decisión pendiente de Raymond: borrarlo o
  dejarlo como borrador.

## Paso 2 — Que el contenido sea parte del motor (pendiente)

1. **Tabla `content_queue` en `data/el_socio.db`**: una fila por pieza (gancho, cuerpo, CTA, nicho,
   formato, estado, fecha de publicación, archivo generado). Mismo patrón que la cola de correos.
2. **`scripts/content_manager.py`** (solo stdlib, igual que el resto): encola, marca publicado y lleva
   el histórico. **Guarda de precios en CÓDIGO, no en el prompt** — reusar las mismas validaciones que ya
   bloquean cifras en `sales_agent.py`. Ninguna pieza sale con un número de dinero, plazo o resultado.
3. **Plantilla Remotion vertical** 1080x1920 a 30 fps alineada a la guía: badge arriba, gancho de 2 s,
   bloques de ~2 s, una palabra resaltada por frase, cierre con `LogoSaludo`. Pasar el patrón de `ffmpeg`
   a `%04d` para no toparse con el techo de 999 frames.
4. **Panel**: una vista más en el servidor de 8787 para ver la cola, aprobar y marcar publicado.
5. **`RESULTADOS_MERCADO.md`**: registrar cada publicación como evento real de canal, igual que ya se
   registra correo y WhatsApp. Sin esto no se sabe si el contenido sirve.

## Paso 3 — Retroalimentación con leads reales (pendiente)

- Cruzar lo que responden los leads (`agent_log`, respuestas clasificadas) con los ganchos publicados:
  qué dolor concreto hace que alguien conteste, y convertirlo en la frase del próximo post.
- Al revés también: la frase que más guarda/comenta la gente entra al banco de ganchos del outreach.
- **Comparte el mismo tope de 0.50 USD/día del agente de ventas.** No es un presupuesto aparte: si el día
  ya se gastó contestando leads, el contenido espera. Vender va primero que publicar.
