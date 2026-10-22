# Hallazgos con paquetes reales

Primer análisis con el prototipo `importer/sonarstage_import` (20 de octubre de 2026).
Dos paquetes descargados por Bryam: *Alegras mis días* (Su Presencia) y *Holy Forever*
(Bethel Music). El audio no está en el repositorio.

## Formatos

| Paquete | Formato | Calidad | Stems |
|---|---|---|---|
| Alegras mis días | RAR con AAC (`.m4A`) | 320 kbps, 44.1 kHz, estéreo | 16 |
| Holy Forever | RAR con MP3 | 320 kbps, 44.1 kHz, estéreo | 18 |

- Todos los stems de un paquete tienen exactamente la misma duración.
- El AAC trae ~60 ms de *priming* (silencio del codificador). ffmpeg lo elimina; un
  decodificador ingenuo desplazaría todos los stems 60 ms respecto a un click en WAV.
- Llegan nombres nuevos: *Click Track, Cues, BGVS, Vox Chop, Aux Drums, Loop, Oohs,
  Synth Bass, Wurli*. Ya están en `roles.py` y en sus pruebas.
- Se necesita leer RAR, no solo ZIP. Se usa `bsdtar`, que viene con macOS (no hay que
  instalar nada); `unrar-cffi` queda como respaldo porque no tiene versión instalable
  para Mac. Con *Alegras mis días*, los dos extraen archivos idénticos (mismo MD5).

## Tempo y compás

| Paquete | BPM | Variación | Compás (bombo) |
|---|---|---|---|
| Alegras mis días | 128.0 | 0.9 ms | 4/4, fase 0 (contraste bajo) |
| Holy Forever | 72.0 | 0.0 ms | 4/4, fase 0 (contraste claro) |

- **El click suena en corcheas** (dos sonidos: tiempo y contratiempo, distintos en
  brillo). Sin separarlos se lee el doble del tempo (256 y 144 BPM).
- **El click no marca el compás**: no hay un tercer sonido para el tiempo 1. El
  primer tiempo se deduce del bombo y se confirma con la guía.
- Ambos empiezan con el click en el segundo 0 (cuenta inicial incluida).

## Guía

- Sin reconocimiento de voz (el modelo no se puede descargar en estos entornos; se
  probará en la Mac), ya se obtiene la forma de la canción: **los avisos principales
  caen en el tiempo 1 cada 4 u 8 compases**, lo que también confirma la cuadrícula.
- Holy Forever: avisos en los compases 6, 10, 18, 26, 34, 42, 52, 60, 68, 76, 84, 92.
- Alegras mis días: 6, 10, 18, 26, 34, 42, 46, 50, 54, 62, 70, 78, 86, 94, 102, 110,
  118, 126, 134, 138, 142.
- Los dos primeros compases tienen la cuenta (avisos cortos en los tiempos 1 y 3).
- Pendiente: decidir si la sección empieza en el compás del aviso o en el siguiente
  (depende de la fuente; se verá con la transcripción).

## Alineación

Correlación de ataques contra el click:

- Stems rítmicos (batería, loops, teclados rítmicos): entre −1 y +11 ms. Sin problemas.
- Stems sostenidos (pads, cuerdas, guitarras, coros): **no se pueden medir** (pico de
  correlación difuso). No se corrigen; se confía en que el paquete es consistente.
- Tolerancia fijada en 15 ms: un problema real de codificador aparece como 25–60 ms.

## Volumen

| Paquete | Mezcla completa | Pico de la suma | Ganancia para −16 LUFS |
|---|---|---|---|
| Alegras mis días | −11.7 LUFS | **+4.4 dBFS** | −4.3 dB |
| Holy Forever | −16.8 LUFS | −0.2 dBFS | +0.8 dB |

- **5.1 dB de diferencia** entre las dos fuentes: confirma que hace falta normalizar
  la canción completa, no solo cada stem.
- La suma de Alegras **satura** (+4.4 dBFS): sin normalizar, la salida a la interfaz
  recortaría.
- Click y guía también difieren entre fuentes (click −23.8 vs −26.0 LUFS; guía −14.3
  vs −18.6 LUFS): se normalizan aparte.

## Mono (perfil de 2 salidas)

- Pérdida de ~3 dB en stems abiertos y no correlacionados es normal.
- Problema real: correlación negativa. *Oohs* (Holy Forever) pierde 5.2 dB en mono.

## Impresión (primera prueba)

`python -m sonarstage_import.prepare` sobre los dos RAR, medido después sobre los FLAC
escritos (no sobre lo que el programa esperaba):

| Canción | Antes | Después | Ganancia | Limitada por |
|---|---|---|---|---|
| Alegras mis días | −11.7 LUFS, pico +4.4 | **−17.1 LUFS, pico −1.0** | −5.4 dB | pico de la mezcla |
| Holy Forever | −16.8 LUFS, pico −0.2 | **−17.7 LUFS, pico −1.0** | −0.8 dB | pico de la mezcla |

- Diferencia entre canciones: de 5.1 dB a **0.6 dB**.
- En las dos manda el techo de pico (−1 dBFS), no el objetivo de −16 LUFS: con mezclas
  de este tipo, el nivel común real ronda −17/−18 LUFS. Conviene bajar el objetivo a
  −18 para que el volumen lo decida siempre el LUFS y no el pico.
- Guía: −18.0 LUFS en ambas. Click: −23.3 y −23.1 LUFS (limitado por su propio pico;
  objetivo ajustado a −23).
- Tiempo: 55–78 s por canción; memoria máxima ~1 GB.

### Espacio: el FLAC impreso pesa más que el original

| Canción | Originales (MP3/AAC 320) | Preparada (FLAC 24 bits) |
|---|---|---|
| Alegras mis días | 182 MB | 456 MB |
| Holy Forever | 233 MB | 699 MB |

Un MP3 decodificado ya no se comprime como el original: ~3 veces más. Con 100
canciones serían ~100 GB. Alternativa a decidir: guardar en la biblioteca solo los
originales y la "receta" (`cancion.json` con ganancias), e imprimir los WAV al
preparar cada show. Solo el cambio de tono, que es más lento, se guardaría impreso.

## Biblioteca con receta y render del show (segunda prueba)

Decisiones aplicadas: objetivo −18 LUFS y biblioteca con originales + receta.

| Canción | Ganancia | Mezcla en el show | Pico | Biblioteca | Show (WAV 48 kHz) |
|---|---|---|---|---|---|
| Holy Forever | −1.2 dB | **−18.0 LUFS** | −1.4 dBFS | 233 MB | 1676 MB |
| Alegras mis días | −6.3 dB | **−18.0 LUFS** | −2.1 dBFS | 182 MB | 1304 MB |

- Ahora manda el volumen objetivo en las dos canciones: diferencia **0.0 dB**.
- Importar sin imprimir: 25–36 s por canción. Renderizar con verificación: 58–76 s
  en el entorno de pruebas (escribe sobre una carpeta compartida; en la Mac será menor).
- **El show en WAV era pesado**: ~1.5 GB por canción, ~18 GB para una boda de 12
  canciones. Decisión: sumar todo el grupo SECUENCIA en un solo archivo estéreo.

## Show agrupado (tercera prueba)

En vivo: Drums, Bass, EG 1 (como en la plantilla de Bryam).

| Canción | Archivos | Tamaño (antes) | Banda + secuencia | Render |
|---|---|---|---|---|
| Holy Forever | 7 | **652 MB** (1676) | −18.0 LUFS, pico −1.4 | 35 s |
| Alegras mis días | 6 | **489 MB** (1304) | −18.0 LUFS, pico −2.1 | 25 s |

- 61–62 % menos espacio: una boda de 12 canciones baja de ~18 GB a ~7 GB.
- La suma no cambia el sonido: banda + secuencia mide igual que todos los stems sueltos.
- Holy Forever trae **Bass y Synth Bass**: con "bass" en vivo, los dos fueron a EN
  VIVO. Si el bajista solo toca uno, eso lo resuelve la matriz de partes (o, por
  ahora, indicar el nombre del stem en lugar del rol: `--live "drums,Bass,EG 1"`).

## Cambio de tono (cuarta prueba)

Rubber Band vía ffmpeg, máxima calidad, solo en stems armónicos (formantes preservados
en voces). Click, guía, batería y percusión no cambian.

> **Actualización (21/10/2026):** el filtro de ffmpeg usaba el motor R2 en modo tiempo
> real. Ahora `transpose` llama a la herramienta `rubberband` (v4.0.0) con el motor R3
> en modo offline. En EG 1 de Holy Forever a −2, R2 bajaba 1.2 LU respecto al original
> y R3 baja 0.6 LU (pierde menos brillo). En una prueba A/B con Ableton
> (Complex Pro), la versión R2 ya sonaba prácticamente igual. Las versiones de esta
> tabla se hicieron con R2.

| Canción | Tono | Stems transpuestos | Tono medido | Tiempo | Volumen del show |
|---|---|---|---|---|---|
| Holy Forever | −2 | 13 de 18 | −1.98 st | 49 s | −18.6 LUFS (limitado por pico) |
| Alegras mis días | +1 | 12 de 16 | +1.04 st | ~35 s | −18.0 LUFS |

- **Duración**: idéntica al original, muestra por muestra.
- **Desfase del procesador**: ~1.7 ms por semitono en envolventes (tarde al bajar,
  temprano al subir) y ~10 ms recortados al final. Es determinista: se calibra por
  canción con ráfagas de tono y se compensa. Residuo en señal de prueba: ≤0.5 ms. En
  ataques de música real el efecto es algo menor, así que el residuo queda en ±1–2 ms
  (sin compensar eran 1–3 ms). En ambos casos, por debajo de lo perceptible.
- **Volumen**: transponer cambia el volumen percibido (−0.4 a −0.8 LU). Cada versión
  guarda su ajuste en `cancion.json` (`key.gainCorrectionDb`), aplicado igual a todos
  los stems de música para no alterar el balance. Holy Forever en −2 llega a −18.6
  porque el techo de pico (−1 dBFS) no deja subir más.
- **Pendiente**: *Loop* (Holy Forever) está clasificado como percusión y no se
  transpone. Si un loop trae notas, desafinaría: la pantalla de confirmación de roles
  debe permitir marcarlo como armónico.

## Secciones y matriz de partes (quinta prueba)

**Dónde empieza cada sección.** Midiendo la energía de la mezcla compás a compás: el
mayor cambio está un compás después del aviso de la guía (Holy Forever: 9 de 13). La
guía anuncia en el compás anterior, a veces en dos compases seguidos ("Coro… dos,
tres"); la sección empieza después del último. Los compases 1–2 son la cuenta (el
bombo de Alegras entra en el compás 3). Con esa regla, las dos canciones quedan en
frases regulares de 4 y 8 compases (antes había secciones de 5, 7 y 9).

**Cuadrícula de actividad** (`parts grid`), guitarras de Alegras mis días: EG 2 sola en
las secciones 3–5, EG 1 desde la 6, EG 3 solo en 6, 12 y 17.

**Matriz de ejemplo**: guitarra con EG 2 en 3–5 y EG 1 en 6–24. Medido sobre la pista
EN VIVO escrita: silencio en cuenta e intro; correlación 1.00 con EG 2 en 3–5 y con
EG 1 desde la 6. En vivo + secuencia: −18.0 LUFS, pico −2.1 (idéntico a sin matriz).

- Las fronteras entre secciones usan fundidos complementarios de 10 ms: la suma de
  en vivo y secuencia es exacta.
- Anacrusa: por defecto la frontera es el tiempo 1. Para las canciones donde una
  parte entra antes, cada sección puede adelantar su inicio N tiempos (`pickupBeats`,
  `parts pickup`); los locators siguen en el tiempo 1.
- Coros: un músico puede dejar lo que cubre sonando en la secuencia a un nivel menor
  (`sequenceLevelDb`, p. ej. −6 dB para reforzar a los cantantes). Su pista EN VIVO
  tiene el resto, así que al desmutearla vuelve al nivel completo. La voz principal,
  en cambio, sale por completo de la secuencia.
- Un mismo stem en la misma sección no puede ser de dos músicos presentes (sonaría
  doble al desmutear): el render lo rechaza.

## Rendimiento

Paquete de 18 stems de 5:23 min: 24 s y 1 GB de memoria máxima, procesando un stem
por vez (cargar todos a la vez agotó 3 GB).

## Primera prueba en Ableton (21/10/2026)

- `Prueba 1.als`, generado por SonarStage, abre en Live 12.4.3 sin errores.
- SonarStage Link carga como superficie de control. Con UDP, Live recibía los comandos
  pero las respuestas no llegaban a la Terminal (firewall de macOS); con TCP funcionan
  `status`, `play`, `repeat`, `release` y `goto`.
- Live recrea los scripts al abrir un documento: el script se instancia de nuevo y vuelve
  a abrir el puerto sin conflicto.

## Nombres de sección desde la guía (21 de octubre)

Whisper `small` (faster-whisper, CPU, int8), sin internet una vez descargado el modelo
(464 MB). Unos 6 s por canción.

| Canción | Idioma detectado | Secciones | Nombradas por la guía | Por regla |
|---|---|---|---|---|
| Holy Forever | inglés | 15 | 15 | 0 |
| Alegras mis días | español | 23 | 21 | 2 |

- La guía anuncia la sección en los 2 compases previos; la cuenta ("one, two…") se
  descarta, también cuando va pegada al nombre ("Chorus two three four" es "Coro").
- Dos reglas para lo que la guía no nombra:
  - la sección que sigue a la cuenta es la **Intro** (Alegras: la guía solo cuenta);
  - un aviso solo de dinámica ("toda la banda", "drums in") **continúa** la sección
    anterior (Alegras, compás 129: "Coro").
- La guía repite nombres ("Verso", "Verso"; "Coro 2", "Coro 2"). Se dejan así: el
  puente salta al **próximo** con ese nombre.
- Errores de transcripción en palabras que no son nombres ("Paje la intensidad" por
  "baja"). Agregar esas frases al vocabulario inicial empeoró otra ("Chorus 2" pasó a
  "course two"), así que el vocabulario se dejó solo con nombres de sección.
- Los avisos de dinámica se guardan en `guide` de cada sección: sirven para la
  pantalla de revisión y, más adelante, para la guía inteligente.
