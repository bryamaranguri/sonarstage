# SonarStage Import

Motor de análisis e impresión de audio, en Python. Se empaqueta dentro de la app:
los usuarios nunca instalan Python.

Responsabilidades (detalle en `docs/arquitectura.md`, sección 1):

- Descomprimir y decodificar paquetes de stems.
- Clasificar y alinear stems.
- Tempo y compases desde el click; secciones desde la guía; tonalidad.
- Mezcla, normalización, cambio de tono y matriz de partes.
- Escribir la canción en la biblioteca según `shared/cancion.schema.json`.

## Prototipo de análisis

Solo lee el paquete; no modifica nada.

```bash
cd importer
pip install -r requirements.txt        # además: ffmpeg/ffprobe en el PATH
python -m sonarstage_import.analyze "<carpeta del paquete descomprimido>" --json reporte.json
python -m pytest tests                 # pruebas que no necesitan audio
```

| Módulo | Qué hace |
|---|---|
| `audio_io` | Decodifica con ffmpeg (respeta gapless MP3 y priming AAC) |
| `roles` | Rol de cada stem por su nombre (español e inglés) |
| `tempo` | Click → tiempos, BPM, cambios; bombo → compás y primer tiempo |
| `align` | Desfase de cada stem respecto al click |
| `levels` | LUFS, pico, actividad y compatibilidad mono; mezcla completa |
| `guide` | Dónde habla la guía, en compás y tiempo |
| `analyze` | Reporte completo de un paquete |
| `extract` | Descomprime ZIP/RAR de forma segura |
| `prepare` | Importa a la biblioteca: originales + receta (`cancion.json`) |
| `transpose` | Versión en otro tono (solo armónicos), compensada en tiempo y volumen |
| `render` | WAV del show: CUES y EN VIVO sueltos, SECUENCIA sumada |

Resultados con paquetes reales: `docs/hallazgos-paquetes.md`.

El cambio de tono necesita un ffmpeg compilado con Rubber Band (el de Homebrew lo trae).

Previsto: faster-whisper (transcripción de la guía).
