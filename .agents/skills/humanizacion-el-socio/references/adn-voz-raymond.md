# ADN de Voz y Video de Raymond ("El Socio")

Perfil vocal y prosódico construido directamente a partir del análisis de las **4 grabaciones reales de Raymond** (explicación libre de El Socio, 2 tomas de Reel A vs B y respuesta a objeción de ChatGPT).

---

## 1. Huella Vocal de Raymond

| Dimensión | Cómo suena Raymond en realidad | Qué evitar siempre |
| :--- | :--- | :--- |
| **Timbre y energía** | Voz masculina grave-media, cálida, relajada y firme. Transmite calma y control. | Voz aguda, sobre-actuada, eufórica o de locutor comercial de radio/TV. |
| **Acento** | Español colombiano natural (toque paisa suave, cotidiano, nada forzado). | Acento "paisa de novela" exagerado o neutro rígido de teleprompter. |
| **Velocidad** | Ágil y fluida en el desarrollo (~145–160 ppm en toma dinámica), bajando ~10% en el cierre. | Lectura lenta/arrastrada que aburre en los primeros 2 segundos, o atropellada sin aire. |
| **Trato** | Tuteo natural y directo (*"te explico"*, *"si necesitas"*, *"lo puedes hacer tú"*). | Trato distante ("estimado emprendedor") o exceso de confianza invasivo. |
| **Estatus** | Seguro, sin necesidad de convencer ni justificarse. Valida objeciones antes de responder. | Sonar rogando, defensivo o prometiendo milagros. |

---

## 2. Diccionario Oral Real (Expresiones y Conectores)

Estas expresiones salieron de forma espontánea en la voz real de Raymond. Úsalas con **moderación quirúrgica** (máximo 1 o 2 por Reel; si pones 5 seguidas suena a parodia):

### Aperturas y transiciones naturales
- `"Bueno, te explico."` → Ideal para Reels explicativos o historias respondiendo dudas.
- `"Sí, obvio."` / `"Obvio que lo puedes hacer tú."` → Ideal para arrancar una respuesta a objeción con estatus alto.
- `"La verdad..."` → Para soltar una verdad incómoda sin sonar agresivo.
- `"Básicamente..."` / `"O sea..."` / `"De hecho..."` → Solo cuando se aterriza un concepto técnico a lenguaje callejero/de negocio.

### Verbos y giros propios (reemplazan jerga corporativa)
| En vez de decir (suena a IA) | Di como Raymond |
| :--- | :--- |
| "Gestionar / implementar / configurar" | **"cuadrar"** (*"cuadrar algo de diseño"*, *"cuadrar el catálogo"*) |
| "Se debe rehacer la muestra" | **"toca repetir muestras"** |
| "El usuario ingresa su requerimiento" | **"solo ve lo que quiere hacer, lo tira ahí, y ahí le solucionan"** |
| "No necesita capacitarse en herramientas" | **"no tiene que ponerse a aprender IA ni hacer cursos, nada"** |
| "Nuestro diferencial competitivo es..." | **"Lo que te entregamos nosotros, ¿qué es?"** → ... → **"Eso te vendemos nosotros."** |
| "Resultados significativamente superiores" | **"te va a salir algo... de otra calidad totalmente diferente."** |

---

## 3. Mapa de Pausas y Prosodia (Cómo modula Raymond)

Analizando sus 2 tomas del Reel del taller y su audio de objeción, su ritmo tiene **5 movimientos claros**:

1. **Entrada con peso en el sujeto (0.0 s – 2.5 s):**
   - Pone énfasis en las primeras 2 palabras y deja correr el gancho sin trabas.
   - Ejemplo real: `Dos marcas sacan colección esta semana.`
2. **Enumeración continua sin cortes robóticos:**
   - Cuando describe el caos del lado A, enlaza las acciones de corrido en una sola respiración.
   - Ejemplo real: `En el primer taller, el patronista adivina las medidas, corta mal y toca repetir muestras.`
3. **Respiración de pivote (~0.35–0.45 s) al pasar de A → B:**
   - Hace una pausa limpia antes de introducir el contraste (`En el segundo, ...`, `Pero con nosotros, ...`, `En cambio, ...`).
   - En la toma más fluida de Raymond, además quita conectores redundantes (*"una manda una foto por WhatsApp al taller, la otra manda una ficha técnica completa"* en vez de cargar con *"y la otra..."*).
4. **Pausa dramática antes del remate (~0.50–0.60 s):**
   - Justo antes de la frase de mayor valor, detiene el ritmo medio segundo para que caiga con peso.
   - Ejemplo real: `Puede que tú crees una imagen normal, pero con nosotros te va a salir algo... de otra calidad totalmente diferente.`
5. **Cierre en 3 golpes firmes (velocidad levemente más pausada):**
   - Separa el contraste final y el sello de marca en tres frases cortas con punto firme.
   - Ejemplo real: `No seas el Taller A. Sé el Taller B. Con tu Socio, te lo solucionamos.`

---

## 4. Trucos de Puntuación para Humanizar el TTS Precargado

El motor [voice_engine.py](../../../scripts/voice_engine.py) soporta `Edge Neural`, `OpenAI gpt-4o-mini-tts` y `ElevenLabs`. Los motores neuronales modernos **responden mejor a puntuación natural que a etiquetas SSML agresivas**.

### Reglas de puntuación prosódica (solo en el texto hablado, nunca ensucian el subtítulo visual)
| Efecto buscado | Puntuación a inyectar en el texto TTS | Duración aproximada que produce |
| :--- | :--- | :--- |
| Micro-respiración antes de pivote (`pero`, `en cambio`, `en el segundo`, `con nosotros`) | `, ` antes o después del pivote (`En el segundo, cortan...`) | ~150–220 ms |
| Separación clara entre idea y consecuencia | `. ` (punto seguido corto, evitando oraciones de más de 16 palabras) | ~320–400 ms |
| Pausa dramática antes del golpe final (máx. 1 por Reel) | `... ` antes del remate (`te va a salir algo... de otra calidad`) | ~450–550 ms |
| Cambio de bloque / escena (lado A → lado B → cierre) | `\n\n` (doble salto de línea en la toma continua) | ~450–600 ms |
| Inflexión conversacional (despierta atención) | `¿...?` en preguntas retóricas cortas (`¿Y qué te entregamos nosotros?`) | Sube entonación natural |

### Calibración por proveedor en [voice_engine.py](../../../scripts/voice_engine.py)
- **Edge Neural (0 USD, activa por defecto tras auditoría de oído v2):**
  - `VOICE_NAME`: `it-IT-GiuseppeMultilingualNeural` (voz multilingüe de 2ª generación con base romance: español fluido, cálido y conversacional sin acento gringo ni tono plano de noticiero). Alternativa más grave/calmada: `fr-FR-RemyMultilingualNeural`. Si prefieres acento colombiano nativo: `es-CO-GonzaloNeural` (también beneficiada por el esculpido de pausas).
  - `VOICE_RATE`: `"+4%"` como tasa base (el motor aplica **prosodia dinámica en 4 tiempos**: gancho `+0%`, lado A `+4%` ágil, pivote B `+1%`, cierre `-6%` más pausado y firme).
  - `VOICE_PITCH`: `"+0Hz"` (cero distorsión metálica del pitch-shift SSML; la calidez grave-media se aplica en EQ limpia `145 Hz` + suavizado de sibilancia `6.5 kHz` en FFmpeg).
  - **Esculpido adaptativo de pausas (`esculpir_pausas_pcm()`):** recorta silencios muertos de TTS (`~0.95 s`) con crossfades cosenoidales de `18 ms` a respiraciones humanas (`0.20–0.24 s` en desarrollo, `0.38 s` en pivote A→B, `0.28 s` entre golpes del cierre) y recalcula al milisegundo los subtítulos de Remotion.
  - **Cierre sin glitch:** usar comillas solo en el texto TTS (`Taller "A"`, `Taller "B"`, nunca `Taller, A`) y flujo directo en `"Con tu Socio te lo solucionamos."`.
- **OpenAI (`gpt-4o-mini-tts`, voz `ash`):**
  - Usar `instructions` explícitas: *"Habla en español colombiano natural y relajado (acento suave de Medellín, nunca caricaturizado). Ritmo ágil y conversacional en el desarrollo, con pausas breves antes del contraste y cierre firme y pausado en frases cortas. Voz grave-media, segura, cero tono de comercial o locutor exagerado."*
- **ElevenLabs (`eleven_multilingual_v2`):**
  - `stability: 0.48`, `similarity_boost: 0.82`, `style: 0.22` (más expresividad conversacional sin perder consistencia).

---

## 5. Ejemplos ANTES (IA plana) vs DESPUÉS (Voz Raymond)

### Caso A: Reel de contraste (Fichas técnicas)
- **ANTES (suena a guion de IA):**
  > ¿Sabías que enviar diseños sin documentación técnica genera sobrecostos en tu producción? Muchos talleres cometen errores al interpretar medidas. Con nuestras soluciones integrales de fichas técnicas podrás optimizar tus procesos y evitar reprocesos innecesarios. Contáctanos hoy.
- **DESPUÉS (ADN Raymond — ritmo real de 24 s):**
  > Dos marcas sacan colección esta semana.
  >
  > Una manda una foto por WhatsApp al taller, la otra manda una ficha técnica completa.
  >
  > En el primer taller, el patronista adivina las medidas, corta mal y toca repetir muestras.
  >
  > En el segundo, cortan a la primera, sin enredos y sin perder tela ni tiempo.
  >
  > No seas el Taller A. Sé el Taller B. Con tu Socio, te lo solucionamos.

### Caso B: Objeción ("¿No lo puedo hacer yo con ChatGPT?")
- **ANTES (defensivo y corporativo):**
  > Aunque cualquier usuario puede utilizar herramientas de inteligencia artificial generativa, nuestro equipo cuenta con amplia experiencia en ingeniería de prompts para garantizar resultados de alta calidad profesional.
- **DESPUÉS (ADN Raymond — estatus alto):**
  > Sí, obvio. Obvio que lo puedes hacer tú. De hecho, lo puede hacer cualquiera que tenga internet y ChatGPT.
  >
  > Lo que te entregamos nosotros, ¿qué es? El tiempo que llevamos afinando prompts y armando procesos que ya funcionan de principio a fin.
  >
  > Eso te vendemos nosotros. Tú puedes sacar una imagen normal, pero con nosotros te va a salir algo... de otra calidad totalmente diferente.

---

## 6. Plan B: Cuándo y cómo pasar a tu voz clonada (ElevenLabs)

Si después de escuchar las pruebas de la voz precargada humanizada (`AndrewMultilingualNeural` y `es-CO-GonzaloNeural`) sientes que todavía se nota un acento extranjero o robótico:
1. Graba **2 a 3 minutos continuos** con el micrófono cerca en un cuarto sin eco (sin ventilador de fondo), leyendo 2 Reels y 2 explicaciones libres con la misma energía de tus Audios 3 y 4.
2. Crea un **Instant Voice Clone** (o Professional Voice Clone) en ElevenLabs con esos audios.
3. Configura en `.env`:
   - `VOICE_PROVIDER=elevenlabs`
   - `ELEVENLABS_API_KEY=...`
   - `ELEVENLABS_VOICE_ID=<tu_voice_id>`
4. Mantén activa la misma función `humanizar_texto_para_voz()` de [voice_engine.py](../../../scripts/voice_engine.py): con tu voz clonada, las pausas y la puntuación prosódica hacen que el resultado sea prácticamente indistinguible de una grabación manual.
