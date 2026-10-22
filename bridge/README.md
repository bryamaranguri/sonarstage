# SonarStage Link

Remote Script para Ableton Live 12: deja que SonarStage (y por ahora la Terminal)
controle el show. Funciona en cualquier edición de Live, sin Max for Live.

## Instalar (una vez)

1. Copia la carpeta **`bridge/SonarStageLink`** completa a
   `~/Music/Ableton/User Library/Remote Scripts/`
   (si no existe la carpeta `Remote Scripts`, créala).
2. Cierra y vuelve a abrir Ableton.
3. **Preferencias → Link/Tempo/MIDI → Control Surface**: en una fila libre elige
   **SonarStageLink**. *Input* y *Output* quedan en *None*.
4. Abajo, en la barra de estado de Live, aparece **"SonarStage Link conectado"**.

Al actualizar el script, vuelve a copiar la carpeta y reinicia Ableton.

## Probar desde la Terminal

Con un show abierto (por ejemplo `material/shows/Prueba 1`):

```bash
cd ~/Ing/01-proj/sonar-stage/sonarstage/bridge
python3 link.py status                 # dónde estás
python3 link.py watch                  # estado en vivo (Ctrl+C para salir)
python3 link.py play
python3 link.py repeat                 # repite la sección actual hasta...
python3 link.py release                # ...soltarla: sigue a la siguiente
python3 link.py goto "Sección 3"       # al terminar la sección actual, salta a la 3
python3 link.py next                   # al terminar la sección actual, a la siguiente
python3 link.py cancel                 # cancela un salto pendiente
python3 link.py next-song              # se detiene y se ubica en la siguiente canción
python3 link.py song 2
python3 link.py unmute "Bajo"          # emergencia: suena la pista del bajista
python3 link.py mute "Bajo"
python3 link.py autostop off           # no detenerse al llegar a la siguiente canción
```

## Cómo funciona

- **Canciones y secciones** salen de los locators del show: `"2. Alegras mis días"`
  abre una canción; los demás locators son secciones.
- **Repetir**: activa el loop de Live sobre la sección actual. Al soltar, la canción sigue.
- **Ir a una sección**: el salto queda pendiente y se dispara durante el último compás
  de la sección actual con cuantización de 1 compás. Live lo ejecuta en el siguiente
  tiempo 1, justo donde termina la sección. Detenido, salta de inmediato.
- **Parada automática**: al llegar a la siguiente canción, se detiene y queda ubicado
  ahí; un *play* la empieza.
- Los nombres de sección se buscan dentro de la canción actual.

## Protocolo

**TCP** en `127.0.0.1:11010` (solo esta Mac): cada mensaje es una línea de JSON y recibe
una línea de JSON con `{"ok", "error"?, "state"}`. Se usa TCP y no UDP porque en una Mac
real el firewall descartaba las respuestas UDP hacia `python3`; por TCP la respuesta
vuelve por la conexión que abrió el cliente. Comandos: `status`, `refresh`, `play`
(`continue`), `stop`, `goto` (`section`, `any_song`), `next_section`, `repeat`,
`release`, `cancel`, `song` (`number`), `next_song`, `mute` (`track`, `on`),
`autostop` (`on`).

`state`: `playing`, `beat`, `tempo`, `song`, `song_title`, `section`, `section_bar`,
`section_bars`, `loop`, `pending`, `autostop`.

Se eligió JSON en vez de OSC porque ambos lados son nuestros y es más fácil de depurar;
un adaptador OSC se puede sumar si hace falta integrar otros equipos.

## Si algo falla

- `Ableton no responde`: revisa que SonarStageLink esté elegido en *Control Surface* y
  que Live esté abierto.
- Registro de Live: `~/Library/Preferences/Ableton/Live 12.4.3/Log.txt` (busca
  `SonarStageLink`).

## Archivos

| Archivo | Qué es |
|---|---|
| `SonarStageLink/core.py` | Lógica del show (se prueba sin Ableton) |
| `SonarStageLink/surface.py` | Conexión con Live: socket y ciclo cada ~100 ms |
| `link.py` | Cliente de prueba para la Terminal |
| `tests/` | Pruebas con un Live simulado (`python3 -m pytest bridge/tests`) |
