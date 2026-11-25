# Prompt para continuar (pegar en una conversación nueva)

Continúa el trabajo en El Socio. Lee primero `ESTADO.md`, `contexto/MODO_TRABAJO.md` y
`CLAUDE.md`. Lo que sigue pendiente, en orden de prioridad:

## 1. Reponer prospectos — es lo que bloquea todo lo demás
Solo quedan **10 leads**. No alcanzan ni para un día (el tope son 15 correos diarios). Se
descartaron 116 buzones de empresa (`info@`, `contacto@`, `lmvjewelry@`) porque le estábamos
escribiendo a buzones, no a personas que deciden.

El buscador (`scripts/prospect_hunter.py`) **NO usa IA**: es scraping puro, descubrir
prospectos cuesta **0 USD**. Córrelo para llenar la cola.

Lo que hay que verificar al correrlo: que con el filtro estricto (solo personas reales) siga
encontrando suficientes para 15 correos al día. **Si no alcanza, se amplían las consultas de
búsqueda — NO se relaja el filtro**, que es justo lo que nos tenía escribiéndole a `info@`.

## 2. Revisar los proyectos vecinos en `~/Desktop/Proyectos_IA/`
Están "Tu Parche En Vivo" y "Aconcagua", y no los he mirado. Quiero saber si comparten la
cuenta de Gmail (`elsociotuia@gmail.com`), el número de WhatsApp o las cuentas de Meta con El
Socio: si otro proyecto manda correos desde la misma cuenta, me está quemando la reputación de
envío y por ahí pueden venir los bloqueos.

Contexto: el 25-nov Meta unificó `tuparcheenvivo`, `elsociotuiaa` y mi Facebook en una misma
cuenta, y el usuario de Instagram cambió de `elsociotuiaa` a `elsociotuia`. Verifica que El
Socio siga publicando en la cuenta correcta (`17841438802416058`) y que nada se cruce.

## 3. Afinar los últimos dudosos del filtro de personas
Todavía pasan como persona cuando son marcas: `cafealtoperfil@gmail.com`, `acuattro@gmail.com`,
`ccialviva@ccviva.com`, `taro@tatoestudio.com`. La regla de subcadena en
`_parece_correo_de_persona` exige 5+ letras y "cafe" tiene 4.

## 4. Medir el primer día real de correos a personas
Hasta ahora: 26 correos enviados, **0 respuestas** — pero 18 de esos 26 fueron a
`info@`/`contacto@`, así que esa muestra no prueba nada. Los próximos van a personas con su
nombre; esa es la primera medición honesta.

Si a los ~40 correos sanos sigue en 0, el problema ya no es la entrega ni el destinatario: es
el ángulo o el nicho, y hay que cambiar el mensaje, no el motor.

## 5. Decidir si el contenido se queda visible
Las 6 piezas del 25-nov sí se publicaron, pero Raymond las archivó. Archivar deja el contenido
invisible y sin métricas, así que `sincronizar_resultados_ig` (que aprende las mejores horas
según seguidores reales) se queda sin datos. Si el objetivo es conseguir clientes por redes,
hay que dejarlas visibles.

---

## Reglas que no se negocian
- **Presupuesto**: 0.50 USD/día compartido. Reserva de ventas 0.41, contenido 0.09, y el
  contenido solo gasta si hay menos de 6 piezas listas (`CONTENT_COLCHON_PIEZAS`). Publicar no
  cuesta IA; crear sí.
- **Instagram**: 3 piezas/día, 1 cada 75 min. Nada de ráfagas — la cuenta anterior
  (`inmocolombia`) ya fue restringida por eso. El panel 8787 publica saltándose la pausa a
  propósito: ese botón es de Raymond, no tocarlo.
- **WhatsApp e Instagram DM en frío NO son automatizables**: WhatsApp masivo desde el número
  personal lo bloquea, y la API de Meta no permite iniciar conversaciones, solo responder
  dentro de 24h. Si se usan, es Raymond a mano. No proponerlo como parte del flujo.
- **Nada de trabajo manual suyo**: el objetivo es que El Socio lo haga solo. Si una táctica
  exige que Raymond ejecute pasos a mano, se descarta, no se le asigna a él.
- **Raymond no programa**: ejecutar todo, nunca pedirle comandos ni que edite código.
- **Precio y link de pago**: solo los pone Raymond. El agente nunca cotiza.
- Correr las **257 pruebas** (`test_sales_agent`, `test_autonomous_brain`,
  `test_content_manager`) antes de dar algo por bueno.

## Estado del motor
`com.elsocio.cerebro` (launchd, cada 15 min) corre solo y encadena: IMAP+landing →
`prospect_hunter` → `sales_agent` → SMTP → `content_brain` → `ig_publisher` → panel 8787.
Todo vive en `data/el_socio.db`, que nunca se sube a Git.
