# SonarStage Import

Motor de análisis e impresión de audio, en Python. Se empaqueta dentro de la app:
los usuarios nunca instalan Python.

Responsabilidades (detalle en `docs/arquitectura.md`, sección 1):

- Descomprimir y decodificar paquetes de stems.
- Clasificar y alinear stems.
- Tempo y compases desde el click; secciones desde la guía; tonalidad.
- Mezcla, normalización, cambio de tono y matriz de partes.
- Escribir la canción en la biblioteca según `shared/cancion.schema.json`.

Librerías previstas: ffmpeg (decodificación), librosa / numpy (análisis),
faster-whisper (guía), pyloudnorm (LUFS), Rubber Band (tono), soundfile (FLAC/WAV).
