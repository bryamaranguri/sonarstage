# Arquitectura

## Visión general

```
 Paquete de stems (ZIP/RAR, WAV/MP3)
            │
            ▼
 ┌────────────────────────┐        ┌──────────────────────────┐
 │  SonarStage Import     │──────▶ │  Biblioteca (SSD externo) │
 │  análisis + impresión  │        │  originales + preparadas  │
 └────────────────────────┘        └──────────────────────────┘
                                               │  "Preparar show"
                                               ▼
                                   ┌──────────────────────────┐
                                   │  Show (disco interno)    │
                                   │  proyecto .als + WAV      │
                                   └──────────────────────────┘
                                               │
 Micrófono (voz) ─▶ ┌────────────────────┐  OSC │
 Pedal MIDI ──────▶ │  App SonarStage    │◀────▶│  SonarStage Link
 Ventana Mac ─────▶ │  (control en vivo) │      │  (Remote Script en Ableton)
                    └────────────────────┘
                              │ estado del show (HTTPS)
                              ▼
                    SonarMaster · modo show (iPad, opcional)
```

## Componentes

| Componente | Tecnología prevista | Carpeta |
|---|---|---|
| App de escritorio (UI, biblioteca, shows) | **Tauri + React** | `app/` |
| Motor: audio, control de Ableton (OSC), voz | **Python** empaquetado como *sidecar* de Tauri | `importer/` |
| Puente con Ableton | MIDI Remote Script en Python (funciona sin Max for Live) | `bridge/` |
| Formatos compartidos | JSON Schema | `shared/` |
| Visor de cifrados | Modo show dentro de SonarMaster (repo aparte) | — |

### Decisión: Tauri + React + motor en Python (21/10/2026)

- **Python para el motor.** El trabajo pesado corre en librerías nativas (ffmpeg, Rubber
  Band, NumPy/SciPy, Whisper); reescribir en Rust o Go no lo aceleraría. Python tiene el
  mejor ecosistema de audio y el motor ya existe con pruebas.
- **Tauri en lugar de Electron.** La app corre junto a Ableton en una MacBook Air M1:
  Tauri usa el WebKit de macOS y consume mucha menos memoria que un Chromium embebido.
- **Reparto:** React dibuja; Rust (capa delgada) abre la ventana, lanza el motor
  empaquetado (PyInstaller) como *sidecar* y pasa mensajes; Python hace audio, OSC con
  Ableton, micrófono y voz.
- Costo asumido: el motor empaquetado pesa ~150–250 MB, más el modelo de Whisper que se
  descarga la primera vez. Diferencias menores de CSS entre WebKit y Chrome.

## 1. Importador

Entrada: ZIP, RAR o carpeta con WAV, MP3, M4A, FLAC o AIFF.

1. **Descomprimir** en una carpeta temporal aislada.
2. **Decodificar** todo a PCM. En MP3, respetar el encabezado de *gapless* para
   eliminar el silencio inicial del codificador.
3. **Clasificar stems** por nombre (diccionario español/inglés: click, guía, drums,
   bass, EG, AG, keys, piano, organ, pad, synth, strings, vocals, choir, perc, FX,
   secuencia/track/full mix). Si el nombre no alcanza, clasificador de audio.
   El usuario confirma y la app aprende de sus correcciones.
4. **Alinear**: comparar ataques de cada stem contra el click y corregir o avisar
   desfases (típicos en MP3 de distintos codificadores).
5. **Tempo y compases desde el click**: detección de golpes; el acento del click da
   el primer tiempo. Resultado: mapa de tempo y posiciones de compás.
6. **Secciones desde la guía**: transcripción offline (Whisper) en español o inglés;
   los nombres ("intro", "verso 2", "coro", "puente"…) se ajustan al compás más cercano.
7. **Tonalidad**: estimación sobre stems armónicos; el usuario confirma.
8. **Revisión**: pantalla para corregir secciones, tempo, tono y clasificación.

### Impresión (salida preparada)

- **Mezcla por plantilla de roles**, luego **normalización de la canción completa**
  (todos los stems, incluidos los de en vivo) a un objetivo LUFS común con limitador
  de picos. Ajuste opcional por canción ("balada −2 dB").
- **Click y guía** se normalizan aparte a un nivel fijo.
- **Cambio de tono** (máx. ±2–3 semitonos en la práctica) solo en stems armónicos y
  voces; nunca en click, guía ni percusión. Procesado offline (Rubber Band).
- **Matriz de partes**: para cada instrumento con varios stems (EG 1–4, keys…) se
  imprimen dos archivos: `<rol> en vivo` (lo que cubre el músico, sección por
  sección) y `<rol> secuencia` (el resto). Si un músico falla, se desmutea
  `<rol> en vivo` y suena exactamente lo que estaba tocando.
- **Secuencia premezclada**: si el paquete trae stems, se usan los stems y la
  premezcla queda como respaldo. Si solo trae premezcla, va a la pista SECUENCIA
  (separación con IA, p. ej. Demucs, queda para una etapa posterior).
- **Compatibilidad mono**: medir correlación estéreo y avisar cuando un stem pierde
  contenido al sumarse a mono (perfil de 2 salidas).
- Frecuencia de muestreo única por usuario (la de su interfaz).

## 2. Biblioteca

```
Biblioteca/
└── <Nombre de la canción>/
    ├── originales/        ← tal como llegaron (MP3 se queda en MP3)
    ├── cancion.json       ← la receta: roles, ganancias, tempo, secciones (shared/cancion.schema.json)
    ├── analisis.json      ← reporte completo del importador
    └── preparada/<tono>/  ← solo versiones transpuestas (lentas de calcular), en FLAC
```

- **Biblioteca = originales + receta.** Las ganancias se aplican al preparar el show
  (`render.py`), que toma segundos por canción. Imprimir FLAC en la biblioteca ocupaba
  ~3 veces lo que el MP3 original y no aportaba nada.
- Solo las versiones con cambio de tono se guardan impresas.
- Respaldo recomendado: segunda copia en otro disco o en la nube.

## 3. Shows

"Preparar show":

1. Elegir canciones (orden editable) y **canciones de reserva** fuera del setlist.
2. Aplicar la **configuración semanal** (quién toca qué) y la matriz de partes de la banda.
3. Revisar espacio en el disco interno.
4. Renderizar a WAV en el disco interno (`render.py`) y **verificar** cada archivo:
   CUES y cada stem de EN VIVO como archivos sueltos; todo lo de SECUENCIA **sumado en
   un solo archivo estéreo** (nunca se mutea por separado; ahorra ~60 % de espacio y
   pistas). Un `show.json` por canción describe archivos y grupos para el generador.
5. Generar el `.als` con el formato de Live 12.0 (lo abren todas las versiones 12.x), siguiendo `docs/plantilla.md`:
   pistas fijas por rol, locators por canción y sección, espacio entre canciones,
   ruteo según el perfil de salidas.
6. Abrir el proyecto en Ableton.

Después del show, un botón borra la copia del disco interno.

### Generación del `.als` (`ableton.py`)

- **Clonado de la plantilla del usuario**: pistas, clips y envolventes se copian de un set
  guardado por Live y solo se cambian nombres, colores, ruteo, posiciones y archivos. El
  formato no está documentado; clonar evita escribir estructuras a ciegas. El archivo
  declara la versión de la plantilla (hoy 12.0.5), así que abre en esa versión o posterior.
- Se renumeran las IDs de objetos automatizables (`*Target`, `Pointee`) y se ajusta
  `NextPointeeId`.
- Canciones seguidas en el arrangement, separadas por una pausa (30 s por defecto) y
  empezando en compás. **Automatización de tempo** en Main: un escalón por canción.
- **Clips sin warp**: el audio suena tal cual, sin estirarse en el escenario.
- **Locators**: uno por canción ("1. Título") y uno por sección.
- Una pista por rol de cue (Click, Guía), aunque cada fuente los nombre distinto.
- Perfil de 2 salidas: Main (secuencia + en vivo) a la salida 1 mono y CUES a la 2 mono.
  Requiere activar las salidas 1 y 2 como mono en *Preferencias → Audio → Output Config*.

### MIDI (`midi.py`, grupo CONTROL)

- Dispositivos MIDI en la banda (`midiDevices`); cambios por sección en `cancion.json`.
- **HX Stomp** (por USB, sin cable de 5 pines): preset = Program Change, snapshot = CC 69
  (0–2 = snapshots 1–3), bloques sueltos con el CC asignado en *Bypass Assign*
  (0–63 apaga, 64–127 prende). El tempo le llega por **MIDI Clock** de Live, que sigue la
  automatización de tempo: no necesita pista de tempo.
- **Consola UAD (Apollo)**: según UAD, el tempo solo se controla por tap tempo vía MIDI
  (nota o CC). El show golpea ese CC en cada tiempo de la cuenta inicial (2 compases),
  así la consola tiene el tempo antes de que entre la música. Pendiente de probar con
  una Apollo real.
- Una pista MIDI por dispositivo, clonada de la pista MIDI de la plantilla; un clip por
  cambio, con `ProgramChange` y envolventes de CC (`ControllerTargets.N` = CC N−2).
- La plantilla que tiene la pista MIDI es `referencia-midi.als` (Live 12.4.3): el show
  declara esa versión.
- Pendiente: ruteo de salida de las pistas MIDI (hoy quedan en *None*).

### Perfiles de salida

| Perfil | Salida 1 | Salida 2 | Resto |
|---|---|---|---|
| 2 salidas | Secuencia (mono) | Click + guía | — |
| 6 / 8 salidas | Secuencia L/R | Click, guía por separado | Grupos de stems |

## 4. Control en vivo

Funciones mínimas (paridad con AbleSet / Setlist / Playback, ver `referencias.md`):

- Setlist editable al vuelo: reordenar, excluir, agregar canciones de reserva.
- Avance automático, parada automática, pausa.
- Saltos y loops **cuantizados** (fin de sección, 1 o 2 compases).
- **Extender sección**: mantener la sección actual en loop hasta liberarla.
- Guía inteligente: se silencia cuando el salto no es lineal; aviso hablado de la
  próxima sección a toda la banda.
- Mutear/desmutear al instante cualquier `<rol> en vivo`.
- Vigilancia de faders con botón "restaurar mezcla".

### Voz

- Micrófono dinámico por una entrada de la interfaz, usado solo por el director.
- Reconocimiento **offline**, vocabulario cerrado, palabra de activación
  ("Secuencia, repetimos el coro").
- Confirmación audible por el canal del click.
- Ejecución cuantizada: basta con decirlo unos tiempos antes del final de la sección.
- El pedal MIDI se agrega después como control principal y respaldo.

### Puente con Ableton

MIDI Remote Script en Python (`bridge/`), comunicado con la app por **líneas de JSON sobre TCP local**
(`127.0.0.1:11010`; JSON en vez de OSC porque ambos lados son nuestros; TCP en vez de
UDP porque el firewall de macOS descartaba las respuestas UDP). Lee y controla
transporte, locators, loops, mute de pistas y posición. Se instala copiándolo a la
carpeta de Remote Scripts del usuario (lo hace el asistente); el usuario solo lo
elige en *Preferencias → Link/Tempo/MIDI → Superficie de control*.

## 5. Integración con SonarMaster

SonarMaster está en Vercel (serverless), así que no hay WebSockets persistentes.

- La Mac crea una **sesión de show** (código para unirse + clave de publicación).
- La Mac publica **estado con horario**, no comandos: canción, sección, hora de
  inicio de la sección, tempo, próxima sección y cuándo empieza, tono en que suena.
- El iPad avanza con su propio reloj y consulta cada 1–2 s para corregirse.
  Un corte breve de internet no lo desincroniza.
- SonarMaster transpone el cifrado al tono que suena y sigue las secciones
  (`[CORO]`, `[VERSO]`… coinciden con las de la guía).
- El iPad guarda el set del día: sin conexión, se pasa de canción manualmente.
- Quien entra con el código ve solo los cifrados de ese setlist, aunque sean privados.

Pendientes en SonarMaster: compás distinto de 4/4 (6/8 es común en iglesia),
importación de PDF a texto, resaltar el compás actual (etapa posterior).

## 6. Instalación y distribución

- Un `.dmg` con todo incluido (Python, modelos, dependencias).
- Asistente de primer arranque: instala el Remote Script, descarga el modelo de voz,
  configura biblioteca, interfaz y banda.
- Sin cuenta de desarrollador de Apple: la primera apertura requiere
  clic derecho → Abrir (documentarlo con capturas).
- Licencias: no se vende, así que componentes GPL (Rubber Band) son aceptables
  para uso privado.
