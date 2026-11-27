---
name: humanizacion-el-socio
description: >-
  Humaniza guiones de video/Reels, locución TTS y correos de ventas/seguimiento
  de El Socio aplicando el ADN real de Raymond (vocabulario colombiano sobrio,
  cadencia hablada, pausas de contraste, puntuación prosódica y estructura de
  correos sin huella de IA). Activar SIEMPRE antes de entregar, generar o revisar
  cualquier guion de video, audio de locución, correo frío, seguimiento o
  respuesta a un cliente de El Socio.
---

# Humanización El Socio (ADN real de Raymond)

Esta skill traduce cualquier borrador de **video/voz** o **correo** de El Socio a la forma real en que habla y escribe **Raymond** en Colombia: cercano, directo, sobrio, con estatus tranquilo y cero palabrería de IA o marketing.

> **Principio rector:** Si un texto suena a "copywriter de agencia", a "locutor de comercial" o a "plantilla masiva", se reescribe desde cero. Raymond nunca ruega, nunca adula de más y nunca explica en tres frases lo que cabe en una.

---

## Reglas transversales (aplican a voz y a correos)

1. **Español colombiano real, cero caricatura:** natural, relajado y claro. Nunca forzar jerga exagerada ("parcero", "qué más pues mi rey") ni caer en español neutro de doblaje ("ordenador", "vale", "os cuento").
2. **Cero cifras ni precios:** hereda la regla inquebrantable de El Socio (nunca poner valores, porcentajes, plazos numéricos ni links de pago).
3. **Cero vocabulario de IA o folleto:** prohibido usar *revolucionario, solución integral, en el mundo actual, en la era digital, potencia, transforma tu negocio, lleva tu negocio al siguiente nivel, optimizar procesos, cuello de botella operativo, maximizar, sin más preámbulos, estimado cliente, saludos cordiales, quedo a su entera disposición*.
4. **Cero adornos de marketing:** `0` signos de exclamación (`!`), `0` emojis decorativos (`🚀🔥✨💡🎯`), `0` viñetas en primer contacto, `0` guiones largos (`—`) decorativos.
5. **Estatus tranquilo (sin ponerse a la defensiva):** ante objeciones ("¿no lo puedo hacer yo con ChatGPT?"), primero se valida sin pelear (*"Sí, obvio. Lo puede hacer cualquiera..."*) y luego se muestra el valor real en seco (*"Eso te vendemos nosotros"*).

---

## Modo 1: Guiones de Video y Voz TTS (Reels / Stories)

Consulta el manual completo en [adn-voz-raymond.md](./references/adn-voz-raymond.md).

### Flujo obligatorio antes de pasar un guion a [voice_engine.py](../../../scripts/voice_engine.py)
1. **Escribe para el oído, no para la vista:** lee mentalmente el guion en voz alta. Si te falta el aire en una frase o suena acartonada al pronunciarla, pártela o cámbiala por verbos cotidianos (*"cuadrar"*, *"toca"*, *"mandar"*, *"quitarse de encima"*).
2. **Trato:** tuteo natural (*"te explico"*, *"si necesitas"*, *"no seas..."*).
3. **Usa la cadencia en 4 tiempos de Raymond:**
   - **Gancho firme (primeras 2–3 palabras con peso):** entra directo al sujeto o tensión sin saludos (*"Dos marcas sacan colección esta semana."*).
   - **Desarrollo corrido (lado A vs lado B):** enumeraciones cortas en una sola respiración (*"adivina las medidas, corta mal y toca repetir muestras"*).
   - **Pausa de pivote antes del contraste y del remate:** marca respiración clara antes del giro (`En el segundo, ...`, `Pero con nosotros...`).
   - **Cierre en 3 golpes secos:** baja ligeramente el ritmo y clava tres frases cortas con punto firme (*"No seas el Taller A. Sé el Taller B. Con tu Socio, te lo solucionamos."*).
4. **Inyecta expresiones reales con dosificación (máximo 1–2 por guion):** *"Bueno, te explico."*, *"La verdad..."*, *"Básicamente..."*, *"Sí, obvio."*, *"toca..."*, *"cuadrar..."*, o una pregunta retórica corta (*"¿Qué es lo que te entregamos nosotros?"*). Nunca amontones varias muletillas en un mismo Reel de 20 segundos.
5. **Aplica puntuación prosódica para el TTS:**
   - `, ` antes de conectores de contraste (`pero`, `en cambio`, `en el segundo`, `con nosotros`) para generar micro-pausa natural.
   - `... ` (solo 1 vez por guion, antes del remate fuerte) para replicar la pausa dramática de ~0.5 s de Raymond.
   - Punto seguido firme (`. `) en los 3 golpes del cierre.
   - **Nunca** alteres los subtítulos visuales en pantalla con signos raros; la puntuación prosódica va solo en la pista de locución (`humanizar_texto_para_voz()` en [voice_engine.py](../../../scripts/voice_engine.py)).

### Checklist de salida (Voz/Video)
- [ ] ¿Dura entre 18 y 28 segundos leído a ritmo natural?
- [ ] ¿Usa sustantivos concretos y cotidianos en vez de abstracciones?
- [ ] ¿Tiene una pausa clara entre el caos (A) y la solución (B)?
- [ ] ¿El cierre entra en 3 golpes firmes sin tono de locutor exagerado?
- [ ] ¿Pasa `sales_agent.revisar_guarda_precios()` sin cifras ni números?

---

## Modo 2: Correos (Fríos, Seguimientos y Respuestas)

Consulta el manual completo y ejemplos reales en [adn-correos-raymond.md](./references/adn-correos-raymond.md).

### Flujo obligatorio antes de enviar o aprobar un correo
1. **Define el registro según el destinatario:**
   - **Marca, taller o estudio (sin nombre de persona):** trato respetuoso y sobrio en **ustedes** → `Buen día, señores [Marca],` o `Señores [Marca],` o `Buen día, ¿cómo están en [Marca]?`
   - **Persona con nombre propio o alguien que te escribió primero:** cercano y directo en **tú** → `Hola [Nombre],` o `¿Cómo estás? Buenas tardes.`
2. **Asunto ultra corto (1 a 4 palabras, natural, sin tono de venta):**
   - Sí: `Makeno`, `Nómada`, `duda rápida Makeno`, `renders Estudio Nómada`.
   - No: `¿El taller te ha entregado algo distinto?`, `Aumenta tus ventas hoy`.
3. **Estructura de 2 a 3 micro-párrafos (40 a 85 palabras en frío; 25 a 55 en seguimiento/respuesta):**
   - **Párrafo 1:** observación real y concreta de su perfil/web (*"Pasé por su perfil y vi su última colección..."*), sin adulación falsa. Si te escribieron primero, valida directo (*"Sí, claro, cuéntame más o menos qué necesitas..."*).
   - **Párrafo 2:** qué haces en la práctica en **El Socio** para ese caso puntual (fichas técnicas listas para taller, renders antes de obra, fotos de producto listas para tienda), en lenguaje cotidiano.
   - **Párrafo 3:** pregunta o salida de cero fricción (*"¿Les funciona para su formato o ahorita no están en eso?"* / *"Si quieren les muestro un ejemplo y ven si les sirve."*) + cierre opcional *"Quedo atento, muchas gracias."* (sin agregar firma ni doble línea de baja; el motor agrega la firma y la baja automáticamente).
4. **Ortografía limpia con naturalidad real:** conserva tus giros exactos (*"pasé por su perfil"*, *"me surgió la duda"*, *"cuéntame más o menos"*, *"quedo atento, muchas gracias"*), pero corrige tildes, errores de dedo y signos `¿ ?` para proyectar estatus y precisión.
5. **Nombre de marca fijo:** en correos siempre nos presentamos como **El Socio** (nunca mezclar "Tu Socio" en el cuerpo del correo).

### Checklist de salida (Correo)
- [ ] ¿Asunto de 1 a 4 palabras sin signo `!` ni pregunta de vendedor?
- [ ] ¿`0` signos de exclamación (`!`), `0` emojis, `0` viñetas, `0` negritas?
- [ ] ¿Se siente escrito por Raymond en 30 segundos, con ortografía limpia?
- [ ] ¿Sin firma repetida ni línea de baja duplicada?
- [ ] ¿Sin cifras, precios ni links no autorizados?

---

## Archivos del motor conectados a esta skill
- Prompt compartido de ventas y contenido: [humanizer.md](../../../.claude/skills/calidad/humanizer.md)
- Prosodia y síntesis de voz: [voice_engine.py](../../../scripts/voice_engine.py) (`humanizar_texto_para_voz()`)
- Guardas y modelos de correo: [sales_agent.py](../../../scripts/sales_agent.py) (`revisar_calidad_humana()`, `MODELOS_CORREO`)
- Dirección oral de guiones: [content_brain.py](../../../scripts/content_brain.py) (`construir_system_prompt_contenido()`)
