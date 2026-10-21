# Configurar la HX Stomp con SonarStage

Guía para conectar la Line 6 HX Stomp a Ableton y que el show le cambie presets,
snapshots y efectos, y le mande el tempo.

## 1. Conexión

- Conecta la HX Stomp a la Mac con el **cable USB** que trae la pedalera. No hace falta
  el cable MIDI de 5 pines ni una interfaz con MIDI: por USB funciona como dispositivo MIDI.
- Si tu Mac solo tiene puertos USB-C, usa un adaptador USB-A → USB-C.
- La HX Stomp también aparece como interfaz de audio. **No la elijas como dispositivo de
  audio en Ableton**: el audio sigue saliendo por tu interfaz.

## 2. En la HX Stomp

Abre **Global Settings → MIDI/Tempo** y revisa:

| Ajuste | Valor | Para qué |
|---|---|---|
| MIDI Base Channel | **1** | Canal en el que escucha (el de la banda en SonarStage). |
| MIDI Clock Rx | **On** (viene así de fábrica) | Seguir el tempo de Ableton. |
| MIDI Over USB | **On**, si aparece la opción | Recibir MIDI por el cable USB. |
| MIDI PC Tx | **Off** (recomendado) | Que la pedalera no devuelva cambios de preset a Ableton. |

**Delays y efectos con tempo:** en cada bloque de delay o modulación, pon el tiempo en
**valor de nota** (por ejemplo 1/4 o 1/8 con puntillo) y no en milisegundos. Así siguen
el tempo que llega por MIDI Clock.

## 3. Snapshots y presets

- Cada preset tiene **3 snapshots**. Úsalos para los cambios dentro de una canción
  (verso, coro, puente): con un solo mensaje cambian varios bloques a la vez.
- SonarStage los cambia con **CC 69**: valor 0 = snapshot 1, 1 = snapshot 2, 2 = snapshot 3.
- Los presets se eligen con **Program Change**. Los presets van en bancos de tres
  (A, B, C), así que el número es `(banco − 1) × 3 + letra`, con A = 0, B = 1, C = 2.
  Por ejemplo: 01A = 0, 01B = 1, 02A = 3, 02B = 4. Compruébalo con un preset la
  primera vez.

## 4. Prender o apagar un bloque con un CC (opcional)

Para casos puntuales en los que no quieras un snapshot nuevo:

1. Abre el menú: presiona **PAGE <** y **PAGE >** a la vez.
2. Presiona la **perilla 1** (*Bypass Assign*).
3. Con la **perilla superior**, elige el bloque.
4. Presiona **PAGE >** y luego la **perilla 3** (*Learn*), y envía el CC desde Ableton.
   También puedes escribir el número a mano con **PAGE >** y la **perilla 1** (*MIDI In*).

Valores de **0 a 63 apagan** el bloque y de **64 a 127 lo prenden**. Anota qué CC le
diste a cada bloque, porque es el que se usa en SonarStage.

## 5. En Ableton (una sola vez)

1. **Preferencias → Link/Tempo/MIDI**.
2. En la lista de puertos, busca la salida (**Output**) **HX Stomp** y activa:
   - **Track**: para que las pistas MIDI le manden presets, snapshots y CC.
   - **Sync**: para mandarle el MIDI Clock (tempo).
3. Pendiente: en `referencia-midi.als`, elegir **HX Stomp** en *MIDI To* de la pista MIDI y
   guardar. Así cada show generado queda conectado automáticamente.

## 6. En SonarStage

La HX Stomp ya está en la banda (`_bandas/mi-banda.json`) como dispositivo
`hx-stomp`, canal 1. Mientras no exista la interfaz, los cambios se cargan así
(el número de sección es el de `parts grid`):

```bash
# Preset 02B (PC 4) y snapshot 1 al empezar la sección 3
python -m sonarstage_import.midi set "<canción>" --band mi-banda.json --device hx-stomp --seccion 3 --preset 4 --snapshot 1

# Snapshot 2 en la sección 6
python -m sonarstage_import.midi set "<canción>" --band mi-banda.json --device hx-stomp --seccion 6 --snapshot 2

# Prender el bloque asignado al CC 20 en la sección 12
python -m sonarstage_import.midi set "<canción>" --band mi-banda.json --device hx-stomp --seccion 12 --cc 20=127

# Ver lo cargado / borrar una sección
python -m sonarstage_import.midi show "<canción>" --band mi-banda.json
python -m sonarstage_import.midi clear "<canción>" --band mi-banda.json --device hx-stomp --seccion 12
```

En la interfaz será un carril más en la línea de tiempo de la matriz.

## Si algo no responde

- **No cambia de preset:** revisa que *Track* esté activo en la salida HX Stomp y que la
  pista MIDI del show tenga *MIDI To* = HX Stomp, en el canal 1.
- **Los delays no siguen el tempo:** revisa *Sync* en Ableton, *MIDI Clock Rx* en la
  pedalera y que el delay esté en valor de nota. Con Ableton detenido no hay reloj.
- **Cambia a un preset equivocado:** revisa la cuenta del Program Change (01A = 0).

Fuentes: [Helix Help – MIDI](https://helixhelp.com/tips-and-guides/universal/midi),
[HX Stomp Owner's Manual](https://line6.com/data/6/0a020a4010c935bb66a4c0c44f/application/pdf/HX%20Stomp%20Manual%20-%20English%20.pdf).
