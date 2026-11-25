# Prompt para continuar (pegar en una conversación nueva)

Continúa el trabajo en El Socio. Lee primero `ESTADO.md`, `contexto/MODO_TRABAJO.md` y
`CLAUDE.md`. Lo que sigue pendiente, en orden:

1. **Revisar los proyectos vecinos en `~/Desktop/Proyectos_IA/`: "Tu Parche En Vivo" y
   "Aconcagua".** No los he mirado todavía. Quiero saber si comparten la cuenta de Gmail
   (`elsociotuia@gmail.com`), el número de WhatsApp o las cuentas de Meta con El Socio, porque
   si otro proyecto manda correos desde la misma cuenta me está quemando la reputación de
   envío. El 25-nov Meta unificó `tuparcheenvivo`, `elsociotuiaa` y mi Facebook en una misma
   cuenta, y el usuario de Instagram cambió de `elsociotuiaa` a `elsociotuia`. Verifica que El
   Socio siga publicando en la cuenta correcta y que nada se cruce.

2. **Averiguar qué pasó con las publicaciones de Instagram del 25-nov.** Meta registra
   `quota_usage: 5` (sí se publicaron), las 2 historias siguen vivas, pero el post y los 2
   reels ya NO están en el perfil: `/media` devuelve vacío y `media_count` es 0. No hay aviso
   de restricción ni de eliminación. Hay que determinar si los borró Raymond a mano o si
   Instagram los quitó. NO reintentar publicar en bucle para averiguarlo.

3. **Reponer prospectos: solo quedan 10 leads.** Se descartaron 116 buzones de empresa. El
   buscador (`prospect_hunter.py`) NO usa IA, así que descubrir prospectos cuesta 0 USD —
   córrelo para llenar la cola. Verifica que con el filtro nuevo (solo personas reales) siga
   encontrando suficientes para los 15 correos diarios; si no alcanza, hay que ampliar las
   consultas de búsqueda, no relajar el filtro.

4. **Afinar los últimos dudosos del filtro de personas.** Todavía pasan como persona:
   `cafealtoperfil@gmail.com`, `acuattro@gmail.com`, `ccialviva@ccviva.com`,
   `taro@tatoestudio.com`. La regla de subcadena exige 5+ letras y "cafe" tiene 4.

5. **Medir el primer día real de correos a personas.** Hasta ahora: 26 correos enviados, 0
   respuestas, pero 18 de esos 26 fueron a `info@`/`contacto@`. Esa muestra no sirve. Los
   próximos van a personas con su nombre; esa es la primera medición honesta. Si a los ~40
   correos sanos sigue en 0, el problema es el ángulo o el nicho, no el motor.

## Reglas que no se negocian
- Presupuesto: 0.50 USD/día compartido. Reserva de ventas 0.41, contenido 0.09, y el contenido
  solo gasta si hay menos de 6 piezas listas (`CONTENT_COLCHON_PIEZAS`). Publicar no cuesta IA.
- Instagram: 3 piezas/día, 1 cada 75 min. Nada de ráfagas: la cuenta anterior ya fue restringida.
- WhatsApp e Instagram DM en frío NO son automatizables (bloqueo de número / la API de Meta no
  deja iniciar conversaciones). Si se usan, es Raymond a mano.
- Raymond no programa: ejecutar todo, nunca pedirle comandos.
- Nada de trabajo manual suyo en el flujo: el objetivo es que El Socio lo haga solo.
- Correr las 257 pruebas antes de dar algo por bueno.
