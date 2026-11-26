# Ciclo de insights → decisión de contenido

Cómo el motor mide sus propias piezas y se corrige solo. Sirve igual para El Socio y para un
cliente con marca propia (mismo código, otro nicho y otra cuenta).

## §1. El objetivo: tasa de guardado, no vistas

Viralidad y venta no son la misma métrica y en nichos de servicio se pelean. Lo que se vuelve
viral es general y emotivo; lo que vende es específico, incómodo y aplicable, y eso tiene techo
de alcance por diseño. Si el motor optimiza vistas, aprende a hacer contenido blando y el cliente
ve crecer el contador sin vender.

**Se optimiza intención, no volumen.** El alcance llega como consecuencia: Instagram distribuye
lo que la gente guarda y comparte. Al revés no funciona.

## §2. Solo los reels enseñan

El embudo tiene etapas distintas y no se miden con la misma vara:

| Formato | Papel en el embudo | ¿Vota en las decisiones del motor? |
|---|---|---|
| Reel | Captación: gente que no conoce la marca | **Sí**, es el único que vota |
| Historia | Retención / remarketing / posventa de quien ya sigue | No |
| Carrusel | Profundiza para quien ya llegó | No (se mide, no decide) |

Dos razones para que la historia no vote: en una cuenta nueva la ven 20 personas y con 20 no hay
señal de nada; y muere a las 24 h, así que no cabe en la ventana de 7 días. Se publica y se mide
para el reporte del cliente, no para aprender.

## §3. Tres métricas, tres cosas distintas que corregir

Un puntaje global no dice qué arreglar. Separados, sí:

| Señal | Qué corrige | Umbral |
|---|---|---|
| `avg_watch_time` ÷ duración | El **gancho** | <50% = el gancho murió |
| (guardados + compartidos) ÷ alcance | El **tema** | >3% fuerte · <1% débil |
| visitas al perfil ÷ alcance | El **cierre** | único indicio de intención de compra |

Pesos del puntaje compuesto (normalizado contra la mediana del propio ciclo, no contra números
absolutos: una cuenta que crece hace ver mal a lo viejo sin que lo viejo fuera peor):

```
guardados           × 3    compartidos      × 3
visitas_perfil      × 2    reacciones       × 2  (solo historias, solo reporte)
comentarios_reales  × 1    comentarios_emoji× 0.1
likes               × 0.2
```

Los likes y el emoji suelto pesan casi nada a propósito: son gratis de dar, así que no dicen nada
de intención. Clasificar el comentario antes de puntuarlo es lo que impide que el motor aprenda a
pedir comentarios en vez de merecerlos.

## §4. Dos capturas por pieza, no una

Un reel a las 2 h no dice nada; a las 24 h da la señal temprana; a los 7 días ya está definido.

```
content_metrics: pieza_id, ventana (24h|7d), alcance, guardados, compartidos,
                 comentarios_reales, comentarios_emoji, likes, visitas_perfil,
                 retencion_pct, capturado_en
```

Tabla aparte de `content_queue` a propósito: las métricas son serie de tiempo. Sobrescribir
`likes_ig` pierde la curva, que es donde está la información.

**Regla operativa: no archivar un reel antes de los 7 días.** Una media archivada sale de Graph
API — su `ig_media_id` responde `does not exist` igual que si nunca se hubiera publicado — y su
dato se pierde sin recuperación: desarchivarla después no devuelve el histórico. Una pieza
archivada antes de la captura de 7 días no aporta nada al aprendizaje del motor. El recolector la
marca `media_archivada_o_borrada` y deja de pedirla.

## §5. Las tres guardas (sin estas el ciclo se autodestruye)

1. **Muestra mínima.** Una dimensión no mueve su peso hasta tener **5 reels medidos a 7 días**.
   Dos piezas buenas no son evidencia. Por debajo de 5 conserva su peso base.
2. **Cuota de exploración: 20-25% fijo.** Una de cada cuatro piezas va a propósito a lo que *no*
   es el ganador actual. Sin esto el motor encuentra un formato que sirve, publica solo ese, y
   nunca descubre el que servía el doble. Es la parte que da rabia y la que lo mantiene aprendiendo
   al mes seis. **No se quita.**
3. **Techo de concentración.** Ningún formato pasa del 50% de un ciclo, ningún tema del 40%. Sin
   tope, a las seis semanas el feed es una sola nota y la audiencia se desconecta — y cuando eso
   aparece en las métricas ya perdiste seguidores.

## §6. El banco de ganchos

El cerebro no inventa el gancho desde cero: saca de un banco de **tipos** (no de textos) —
contradicción, error que todos cometen, confesión, antes/después, pregunta incómoda, dato que
choca. Cada tipo guarda su retención medida **en esa cuenta**. Entran tipos nuevos al analizar un
reel de referencia con `redes/analizar_referencia.sh`.

Copiar un formato viral de otra cuenta es la forma más común de hacer algo que muere: funcionó por
la audiencia, la cara y el momento de ese creador. **Lo que se transfiere es la estructura** (qué
tensión abre en el primer segundo), nunca el contenido.

## §7. La interacción se merece, no se pide

Implementado como guarda en `content_manager.revisar_pieza` (motivo `pide_interaccion`), no como
instrucción del prompt: una instrucción se diluye en tres semanas, una guarda no se negocia.
Bloquea pedir comentario, like, guardado, compartido, seguimiento y "link en bio". Exige pareja
verbo+objeto para no censurar el habla normal ("el taller guarda las telas" pasa).

Lo que sí produce comentario merecido, y va en el guion:
- **Dejar algo sin cerrar** que el espectador quiera resolver.
- **Afirmar algo discutible** con lo que una parte no esté de acuerdo.
- **Nombrar una experiencia específica** que el espectador reconozca y quiera completar con la suya.

## §8. Cadencia

| Cuándo | Qué pasa |
|---|---|
| Diario | Publica + captura ventana 24 h de lo de ayer |
| Semanal | Captura ventana 7 d + recalcula pesos si hay muestra |
| Fin de ciclo (15-20 días, según nicho) | Reconstruye el banco de ideas: retira el fondo, conserva los ángulos ganadores, libera lo más viejo para reuso |
| Mensual | Genera el reporte del cliente (producto de la cita, no mantenimiento técnico) |

## §9. Honestidad de etapa

Con menos de 30 reels medidos **ninguna fórmula es encontrable**: no hay muestra. Las primeras
30-40 piezas son recolección de datos. Lo que el ciclo hace desde el día uno es **impedir piezas
estructuralmente muertas** (sin tensión al arranque, sin motivo para guardar, con frases que no
muestran nada). La parte que aprende y se corrige sola enciende alrededor de la pieza 30. Al
cliente se le dice en esos términos.
