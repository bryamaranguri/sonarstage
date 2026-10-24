# App de escritorio

Interfaz para Mac con **Tauri + React** (decisión en `docs/arquitectura.md`). El motor de
audio es el paquete Python de `importer/`, lanzado como *sidecar*. Reúne:

- Importación y revisión de canciones.
- Biblioteca, configuración semanal y matriz de partes.
- "Preparar show": copia al disco interno, verificación y generación del `.als`.
- Control en vivo y reconocimiento de voz.
- Publicación del estado del show hacia SonarMaster.

Se distribuye como `.dmg` con un asistente de primer arranque.

## Primera versión (24/10/2026): en el navegador

La interfaz (`app/ui`, React + Vite) la sirve el motor (`importer/sonarstage_import/server.py`)
en `http://127.0.0.1:11011`. El envoltorio Tauri y el `.dmg` vienen después.

```bash
cd ~/Ing/01-proj/sonar-stage/sonarstage/app/ui
npm install && npm run build                 # una vez, y cada vez que cambie la interfaz
cd ../../importer && source .venv/bin/activate
python -m sonarstage_import.server --material ../../material          # con Ableton
python -m sonarstage_import.server --material ../../material --demo   # sin Ableton (simulado)
```

Pantallas: **En vivo** (secuencia, secciones, respaldos EN VIVO, voz), **Biblioteca**,
**Show** (armar y preparar), **Ajustes** (interfaz, entradas, volumen de la confirmación).
La matriz de partes llega en la siguiente entrega. Para desarrollar: `npm run dev`
(puerto 5173, reenvía `/api` al motor).
