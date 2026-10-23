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
| `label` | Nombres de sección desde la guía (Whisper, sin internet tras la descarga) |
| `transpose` | Versión en otro tono (solo armónicos), compensada en tiempo y volumen |
| `parts` | Banda, cuadrícula de actividad y matriz de partes por sección |
| `render` | WAV del show: CUES, una pista EN VIVO por músico presente, SECUENCIA sumada |
| `ableton` | Escribe el `.als` clonando pistas y clips de la plantilla del usuario |
| `midi` | Cambios MIDI por sección (presets, snapshots, CC) y pistas de tap tempo |
| `show` | Preparar show: renderiza cada canción y genera el proyecto de Ableton |
| `voice` | Control por voz: micrófono → frases → comandos para SonarStage Link |
| `voice_commands` | Vocabulario cerrado: qué frase es qué comando |
| `link_client` | Cliente TCP de SonarStage Link |
| `voice_prompts` | Frases de confirmación habladas («Coro», «Repetimos»), hechas con las voces de macOS |
| `voice_bench` | Compara motores de voz con frases grabadas (`--record`) |

Resultados con paquetes reales: `docs/hallazgos-paquetes.md`.

El cambio de tono necesita la herramienta `rubberband` v3 o más reciente (motor R3), en el
PATH o indicada con `SONARSTAGE_RUBBERBAND`. La app la incluye junto a ffmpeg.

### Preparar la Mac (desarrollo)

```bash
cd ~/Ing/01-proj/sonar-stage/sonarstage/importer
python3 -m venv .venv && source .venv/bin/activate   # Python 3.9 o más reciente
pip install -r requirements.txt
which ffmpeg || brew install ffmpeg
brew install rubberband                  # cambio de tono, motor R3 (rubberband --version ≥ 3)
```

Nombres de sección (la primera vez descarga el modelo `small`, ~470 MB):

```bash
python -m sonarstage_import.label "../../material/biblioteca/Holy Forever" --model-dir ../../material/modelos
python -m sonarstage_import.label "../../material/biblioteca/Holy Forever" --model-dir ../../material/modelos --apply
```

Control por voz (Ableton abierto con SonarStage Link; el modelo es el mismo de `label`):

```bash
python -m sonarstage_import.voice --devices                      # entradas de audio disponibles
python -m sonarstage_import.voice --device "<interfaz>" --channel 2 --model-dir ../../material/modelos --dry-run
python -m sonarstage_import.voice --device "<interfaz>" --channel 2 --model-dir ../../material/modelos
```

Siempre empieza con la palabra de activación: «Secuencia, repetimos» (una vez más; para
otra, se vuelve a decir), «Secuencia, en bucle» (hasta «seguimos»), «Secuencia,
vamos al puente», «Secuencia, siguiente», «Secuencia, seguimos», «Secuencia, cancela»,
«Secuencia, siguiente canción», «Secuencia, después va la canción tres», «Secuencia,
saltamos la canción dos», «Secuencia, silencia la guitarra» / «activa la guitarra»,
«Secuencia, dale» / «para». Lo que se ejecuta aparece en la barra de estado de Live.

Confirmación hablada (una vez, en la Mac; usa la voz en español de macOS):

```bash
python -m sonarstage_import.voice_prompts ../../material/voces
```

`voice` la toca por la salida del click (`--confirm-channel 2`, `--confirm-gain -6` para
bajarla, `--no-confirm` para quitarla).
