# Roadmap

## Fase 1 — Importador
Donde hoy se pierden ~30 minutos por canción.

- [ ] Descompresión ZIP/RAR y decodificación WAV/MP3 (gapless)
- [ ] Clasificación de stems por nombre + confirmación
- [ ] Alineación de stems contra el click
- [ ] Tempo y compases desde el click
- [ ] Secciones desde la guía (Whisper, es/en)
- [ ] Estimación de tonalidad
- [ ] Mezcla por plantilla de roles + normalización LUFS de la canción
- [ ] Cambio de tono offline en stems armónicos
- [ ] Matriz de partes (`<rol> en vivo` / `<rol> secuencia`)
- [ ] Biblioteca: `cancion.json` + preparadas en FLAC
- [ ] Generador de show `.als` para Live 11 y 12 con perfiles de salida

## Fase 2 — Control en vivo
- [ ] Remote Script + comunicación OSC con la app
- [ ] Setlist al vuelo, avance y parada automáticos
- [ ] Loops y saltos cuantizados, extender sección
- [ ] Guía inteligente
- [ ] Mute/desmute instantáneo de pistas en vivo
- [ ] Control por voz (offline, palabra de activación, confirmación en el click)
- [ ] Pedal MIDI

## Fase 3 — Cifrados
- [ ] Sesión de show en SonarMaster (endpoints + modo show)
- [ ] Transposición y seguimiento de secciones en el iPad
- [ ] Importar PDF a texto

## Fase 4 — Sistema completo
- [ ] Instalador `.dmg` y asistente de primer arranque
- [ ] Letras a proyector (iglesia)
- [ ] Luces por MIDI/DMX
- [ ] Separación de stems para secuencias premezcladas
