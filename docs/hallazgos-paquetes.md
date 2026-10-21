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
- Se necesita leer RAR, no solo ZIP (`unrar-cffi`).

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

## Rendimiento

Paquete de 18 stems de 5:23 min: 24 s y 1 GB de memoria máxima, procesando un stem
por vez (cargar todos a la vez agotó 3 GB).
