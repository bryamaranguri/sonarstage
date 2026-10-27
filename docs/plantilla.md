# Convención de pistas del show

Basada en la plantilla de Bryam (`Bondad de Dios.als`, Live 12.0.5) con mejoras.
El generador de shows crea el proyecto siguiendo estas reglas; no copia un `.als`.

## Plantilla original (referencia)

| Grupo | Color (índice Live) | Pistas | Estado |
|---|---|---|---|
| CUES | 41 (gris) / pistas 13 (blanco) | CLICK, GUIDE | Warp *Beats* |
| PLAYBACKS | 64 (azul) / pistas 24 (morado) | DRUMS, BASS, EG 1–4 | Drums, Bass, EG 1 muteados |
| TRACKS | 1 (naranja) / pistas 3 (amarillo) | VOCALS, SECUENCIA, Keys 1, Organ, Piano, Perc | Vocals muteado |

Observaciones: mezcla en los faders (Drums −1 dB, Bass +2.4 dB, Vocals −0.4 dB,
Perc −6.6 dB); stems a 48 kHz en proyecto a 44.1 kHz; sin locators; salidas aún
sin configurar; nombres con números agregados por Ableton (`8-EG 2`).

## Convención nueva

| Grupo | Función | Colores |
|---|---|---|
| **CUES** | Click, guía y TALKBACK. Nunca pasan por la salida principal. | Gris / blanco |
| **EN VIVO** | Respaldo de lo que toca la banda esa semana: muteado y ya mezclado. | Azul / morado |
| **SECUENCIA** | Todo lo que suena. | Naranja / amarillo |

Reglas:

1. **La app decide el grupo de cada pista** según la configuración semanal y la
   matriz de partes. Si falta el bajista, el bajo pasa a SECUENCIA.
2. **Faders en 0 dB.** La mezcla está impresa en el audio. El fader de cada grupo
   queda como control de emergencia.
3. **Nombres limpios** sin numeración automática (`EG 2`, no `8-EG 2`).
4. **Solo se crean las pistas que usan las canciones del show.**
5. **Sin warp**: todo el audio suena tal cual (el tono se cambia antes, en el
   importador). La cuadrícula sigue al audio con la automatización de tempo, escrita
   desde el mapa de tempo de cada canción. (La plantilla original usaba *Beats*.)
6. Una sola frecuencia de muestreo: la de la interfaz del usuario.
7. **Click MIDI**: una pista con Drum Rack en CUES (clonada de `referencia-click`) y
   un clip MIDI por canción sobre el mapa de tempo: C1 (nota 36) en el tiempo 1, C#1
   (nota 37) en el resto, con los sonidos propios de SonarStage. El click de audio del
   paquete queda muteado como «Click original».

## Roles disponibles

Click · Guide · Drums · Perc · Bass · EG 1–4 (y `EG en vivo` / `EG secuencia`) ·
AG · Keys · Piano · Organ · Synth · Pad · Strings · Lead Vocal · Coros / Choir ·
FX · Secuencia (premezcla) · Extra (sin clasificar)

## Ruteo por perfil

- **2 salidas**: SECUENCIA y EN VIVO → salida 1 (mono). CUES → salida 2.
- **6 / 8 salidas**: secuencia estéreo en 1/2, click y guía en salidas propias,
  grupos de stems en las restantes (a definir con cada interfaz).

## Talkback (micrófono del director)

El micrófono de órdenes llega a los in-ears de la banda junto al click. Al preparar el
show (opción **TALKBACK**, activada por defecto) el generador agrega al grupo CUES una
pista `TALKBACK`:

- **Entrada**: la misma del control por voz (*Ajustes → Entrada del micrófono*), como
  entrada mono. En Live, esa entrada tiene que estar activada como mono en
  *Preferencias → Audio → Configuración de entradas*, igual que las salidas.
- **Monitor: In**, sin clips. Solo deja pasar el micrófono.
- **Salida**: el grupo CUES, o sea la salida del click (la 2 con 2 salidas).

El volumen se maneja en tres puntos que no se mezclan:

1. **Ganancia de la interfaz**: es para el reconocimiento de voz. Se calibra una vez y no
   se toca.
2. **Fader de TALKBACK**: el balance de la voz frente al click y la guía. No afecta al
   reconocimiento, que lee la entrada antes de Ableton. Es la única pista con fader
   propio: no lleva mezcla impresa.
3. **Nivel de la salida del click** en la consola o los in-ears: lo ajusta cada músico.

Las confirmaciones habladas («Coro dos») no pasan por esta pista: el control por voz las
manda directo a la salida del click.

**Gate y nivel guardados.** Si la plantilla tiene una pista de audio llamada `TALKBACK`,
el generador la clona con sus efectos (p. ej. un *Gate* para que el ruido del escenario
no llegue a los in-ears) y su fader. Si no, la pista sale limpia a 0 dB. Cada usuario
la agrega en **su propia** plantilla, guardada en su versión de Live: Bryam en
`referencia-midi.als` (12.4.3); el amigo, en su copia en 12.0. Nunca se pasa una
plantilla guardada en 12.4 a alguien con 12.0.

**Antes de cada show**: la perilla *Monitor Mix* de la SSL 2 va toda hacia **USB**
(playback). Si deja pasar la entrada, el micrófono sale directo por todas las salidas,
también por la 1, y el público escucha las órdenes.

Con 6/8 salidas, el talkback puede ir a una salida propia para que el sonidista lo
mezcle aparte en cada in-ear (pendiente al definir esos perfiles).
