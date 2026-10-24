# Interfaz

Decisiones de diseño de la app (Tauri + React). Prototipo interactivo de la matriz:
artefacto privado "SonarStage · Matriz de partes" (claude.ai), con datos reales de
*Alegras mis días*.

## Estilo (24/10/2026: equipo de estudio, a pedido de Bryam)

Referencia: la estética de los plugins de Neural DSP (capturas de Archetype Mateus Asato y
John Mayer X). Se toma la sensación, no la marca: dibujos propios en CSS/SVG.

- **Sala oscura** con madera cálida desenfocada y luz violeta (sirve en escenario).
- Navegación con **íconos de línea** arriba; **franja de perillas planas** oscuras
  (lecturas), selector tipo preset y textos-botón en mayúsculas; **barra negra** abajo.
- **Módulos de rack azul pizarra con borde cobrizo**, tornillos, título grande crema con
  tracking y subtítulo, filete con marcas, **patas de cobre**.
- Controles: **domos crema** para pulsar (estilo de las perillas del Gravity Tank),
  **interruptores de palanca** ON/OFF, **LED verde**, **medidor de aguja** (cuánto falta
  para el final de la sección; la zona naranja es el último compás, donde se dispara un
  salto), **pantallas** negras con texto ámbar, **faders** con escala (estilo del Reverb).
- Fuentes locales (sin internet en vivo): Manrope, IBM Plex Mono.
- Botones y celdas de al menos 44 px (uso con pantalla táctil o con prisa).

## Pantalla de matriz de partes (aprobada 21/10/2026)

- **Línea de tiempo horizontal, como el arrangement de Ableton**: regla de compases
  arriba (cada 4), fila de secciones con ancho proporcional a sus compases, una pista
  por stem del instrumento (EG 1, EG 2, EG 3…). Nombres de pista fijos a la izquierda;
  scroll horizontal y zoom (22/30/42 px por compás; 22 mantiene una sección de 2
  compases en 44 px).
- Cada bloque es un clip: **morado** si lo toca el músico, **ámbar** si suena y va a la
  secuencia, vacío si no suena. **La altura del bloque** indica cuánto suena el stem
  en esa sección (medido por el importador).
- Clic en un bloque: tomar o dejar ese stem en esa sección.
- Clic en una sección: la selecciona. Debajo, un panel con **escuchar cada stem solo**
  en esa sección y el control de **anacrusa** (poco frecuente: no ocupa columna; en la
  línea de tiempo solo una marca ámbar en el borde de la sección).
- Barra lateral de músicos con **"Toca esta semana"** (configuración semanal).
- Resumen arriba: qué lleva la pista EN VIVO del músico y qué sigue en la secuencia.
- Atajos: volver a lo habitual (stems por defecto en toda la canción) y vaciar.
