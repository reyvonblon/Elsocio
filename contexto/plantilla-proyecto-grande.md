# Plantilla: proyecto grande de El Socio (paso a paso + checklist)

Se usa para todo trabajo grande: aplicaciones, agentes de IA, sistemas, marcas completas, campañas, tiendas, o cualquier cosa que tome más de unos días o supere el rango de precio fijo. Se copia esta plantilla, se rellena por cliente y se va marcando.

---
## PARTE 1. Parámetros de entrada (brief). No se empieza sin esto
- [ ] Cliente y forma de contacto (nombre, correo, WhatsApp)
- [ ] Problema o idea, con sus palabras
- [ ] Objetivo medible: ¿cómo sabremos que quedó bien?
- [ ] Para quién es (usuarios finales)
- [ ] **Qué incluye** (lista concreta)
- [ ] **Qué NO incluye** (lista concreta, muy importante)
- [ ] Entregables y formato (archivos, enlaces, accesos, código)
- [ ] Plazo deseado y fecha límite real, si existe
- [ ] Rango de presupuesto del cliente
- [ ] Qué necesita aportar el cliente (textos, fotos, accesos, decisiones) y para cuándo
- [ ] Quién aprueba cada entrega (una sola persona)
- [ ] Datos sensibles o personales involucrados (cómo se protegen)
- [ ] Revisión de límites: prueba de tres preguntas (legal; no médico/legal/finanzas personales/fraude; resoluble con IA, diseño, software, documentos)
- [ ] Riesgos y dependencias (servicios de terceros, costos mensuales, permisos)

## PARTE 2. Alcance y precio por fases
El dueño fija el precio (el agente nunca). Todo por escrito y aceptado por el cliente.
| Fase | Qué se entrega | Cómo sabemos que está terminada | Plazo | Precio (COP) | Pago |
|---|---|---|---|---|---|
| 0. Diagnóstico | Propuesta, alcance y plan | Cliente aprueba por escrito | | | 100 % antes |
| 1. | | | | | 50 % al empezar / 50 % al entregar |
| 2. | | | | | |
- [ ] Alcance aceptado por escrito (mensaje o correo guardado)
- [ ] Pago inicial recibido antes de empezar cada fase

## PARTE 3. Reglas de control
1. Todo cambio fuera del alcance es una cotización nueva.
2. Máximo 2 rondas de revisión por fase.
3. No se avanza a la siguiente fase sin pagar la anterior.
4. Cada entrega se aprueba por escrito.
5. Costos de terceros (servidores, APIs, dominios) los paga el cliente o se incluyen en el precio de forma explícita.
6. Nunca se prometen resultados de negocio (ventas, seguidores), solo entregables.
7. Si el cliente se demora más de 7 días en responder, se pausa el proyecto y se avisa.

## PARTE 4. Checklist de ejecución (copiar por fase)
**A. Preparación**
- [ ] Brief completo y alcance firmado
- [ ] Pago inicial recibido
- [ ] Carpeta del proyecto y repositorio creados
- [ ] Accesos y claves en un archivo seguro (nunca en el chat; `.env` en `.gitignore`)
- [ ] Archivo `ESTADO.md` creado

**B. Plan**
- [ ] Plan corto escrito (qué se construye, en qué orden, riesgos)
- [ ] Plan aprobado por el dueño antes de construir

**C. Construcción en pasos pequeños**
- [ ] Cada paso es pequeño, se prueba y se guarda (commit sin secretos)
- [ ] Se usa modo de prueba (dry-run / sandbox) antes de cualquier acción real
- [ ] Al terminar cada paso se actualiza `ESTADO.md`

**D. Pruebas**
- [ ] Caso feliz completo de principio a fin
- [ ] Casos de error y datos raros
- [ ] Revisión en celular y en computador, si aplica
- [ ] Sin duplicados, sin datos de prueba mezclados con reales
- [ ] Revisión de tono, ortografía y diseño

**E. Revisión del cliente**
- [ ] Demo o enlace de prueba enviado
- [ ] Comentarios recogidos (máximo 2 rondas)
- [ ] Aprobación por escrito

**F. Entrega y cobro**
- [ ] Cobro del saldo antes de entregar archivos finales o accesos definitivos
- [ ] Entrega de archivos, enlaces y accesos
- [ ] Guía corta de uso para el cliente
- [ ] Confirmación de recibido

**G. Cierre**
- [ ] `ESTADO.md` final y commit sin `.env`
- [ ] Copia de seguridad guardada
- [ ] Permiso del cliente para mostrarlo como caso (o se anonimiza)
- [ ] Pedir una reseña corta
- [ ] Anotar lo aprendido: qué tardó más, qué costó, qué cambiaría

## PARTE 5. Bitácora (una línea por avance)
Fecha | Qué se hizo | Decisión tomada | Siguiente paso

## PARTE 6. Errores comunes a evitar
- Empezar sin alcance escrito ni pago inicial.
- Prometer en el chat algo que no está en el alcance.
- Construir todo de una vez en vez de pasos pequeños probados.
- Dejar claves o contraseñas dentro del código o del repositorio.
- Probar con datos reales o enviar mensajes reales sin dry-run.
- No guardar la aprobación del cliente.
- Olvidar costos mensuales de servicios (el cliente debe saberlo desde el inicio).
- Entregar sin cobrar el saldo.
