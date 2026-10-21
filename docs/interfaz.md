# Interfaz

Decisiones de diseño de la app (Tauri + React). Prototipo interactivo de la matriz:
artefacto privado "SonarStage · Matriz de partes" (claude.ai), con datos reales de
*Alegras mis días*.

## Estilo

- Familia visual de SonarMaster: Lora (títulos), IBM Plex Sans Condensed (texto),
  IBM Plex Mono (números), acento ámbar.
- Fondo oscuro de escenario.
- Colores de grupo de la plantilla de Ableton: **morado = EN VIVO**, **ámbar = SECUENCIA**.
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
