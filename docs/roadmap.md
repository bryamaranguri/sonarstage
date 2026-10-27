# Roadmap

## Fase 1 — Importador
Donde hoy se pierden ~30 minutos por canción.

Prototipo de análisis probado con dos paquetes reales: ver `hallazgos-paquetes.md`.

- [ ] Descompresión ZIP/RAR y decodificación WAV/MP3/AAC (gapless) — *decodificación lista; falta integrar la descompresión*
- [ ] Clasificación de stems por nombre + confirmación — *clasificación lista; falta la confirmación*
- [x] Alineación de stems contra el click (prototipo)
- [x] Tempo, compás y primer tiempo desde click + bombo (prototipo)
- [x] Mapa de tempo completo desde el click (cambios de tempo, ritardandos, paradas) y automatización de tempo del show desde el mapa — *falta abrir `Prueba 4 - mapa de tempo` en Live y comprobar que el metrónomo de Live coincide con el click en el ritardando y después de la parada*
- [x] Click MIDI con Drum Rack sobre el mapa de tempo (acento en el 1), comparado contra el click original; click de audio muteado como «Click original» — *plantilla `referencia-click` en 12.4.3: falta abrir `Prueba 5 - click MIDI` en Live, rehacer la plantilla en 12.0 para el amigo y elegir negras/corcheas por sección*
- [x] Medición de volumen, saturación y compatibilidad mono (prototipo)
- [x] Secciones desde la guía (Whisper, es/en) — *probado con las dos canciones; falta llevarlo a la pantalla de revisión*
- [x] Estimación de tonalidad (stems armónicos; el usuario la confirma en la biblioteca)
- [ ] Mezcla por plantilla de roles + normalización LUFS de la canción
- [x] Cambio de tono offline en stems armónicos (compensación de desfase y de volumen)
- [x] Banda, configuración semanal y matriz de partes (una pista EN VIVO por músico) — *por línea de comandos; falta la interfaz*
- [ ] Biblioteca: `cancion.json` + preparadas en FLAC
- [x] Generador de show `.als` (clonado de la plantilla; perfiles de 2 y 4 salidas) — **abre en Live 12.4.3** (`Prueba 1`)

## Fase 2 — Control en vivo
- [x] Remote Script SonarStage Link (JSON por TCP local) — **probado en Live 12.4.3** (21/10/2026)
- [ ] Setlist al vuelo, avance y parada automáticos
- [x] Loops y saltos cuantizados, extender sección (en el núcleo del puente)
- [x] Guía inteligente — *se silencia mientras hay un salto pendiente o un bucle; falta el aviso hablado de la próxima sección cuando el salto no es lineal*
- [ ] Mute/desmute instantáneo de pistas en vivo
- [ ] Control por voz (offline, palabra de activación, confirmación en el click) — *listo en Terminal con confirmación en la barra de estado de Live; falta probarlo con el micrófono real y la confirmación audible*
- [x] Talkback: el micrófono del director a los in-ears con el click (pista TALKBACK en CUES) — *falta probarlo en Live; el Gate va en una pista TALKBACK de la plantilla de cada usuario*
- [ ] Pedal MIDI

## Fase 3 — Cifrados
- [ ] Sesión de show en SonarMaster (endpoints + modo show)
- [ ] Transposición y seguimiento de secciones en el iPad
- [ ] Importar PDF a texto

## Fase 4 — Sistema completo
- [ ] Instalador `.dmg` y asistente de primer arranque
  - [ ] Incluir `ffmpeg`, `ffprobe` y `rubberband` (≥ 3, motor R3) sin depender de Homebrew: ver `arquitectura.md` → "Binarios nativos dentro del `.dmg`"
- [ ] Letras a proyector (iglesia)
- [ ] Luces por MIDI/DMX
- [ ] Pendiente (amigo): mover niveles de parámetros de plugins en la consola Apollo desde el show. Investigar qué permite controlar la consola por MIDI (la documentación de UAD solo menciona tap tempo).
- [x] Pistas MIDI: HX Stomp (preset/snapshot/CC por sección) y tap tempo para la consola UAD — *pendiente: ruteo a los puertos y prueba con equipos reales*
- [ ] Separación de stems para secuencias premezcladas

- [x] App (primera versión, en el navegador): En vivo, Biblioteca, Show, Matriz de partes, Ajustes — *falta envoltorio Tauri y .dmg; escuchar cada stem solo en la matriz*
