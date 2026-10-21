# App de escritorio

Interfaz para Mac con **Tauri + React** (decisión en `docs/arquitectura.md`). El motor de
audio es el paquete Python de `importer/`, lanzado como *sidecar*. Reúne:

- Importación y revisión de canciones.
- Biblioteca, configuración semanal y matriz de partes.
- "Preparar show": copia al disco interno, verificación y generación del `.als`.
- Control en vivo y reconocimiento de voz.
- Publicación del estado del show hacia SonarMaster.

Se distribuye como `.dmg` con un asistente de primer arranque.
