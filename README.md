# SonarStage

Preparar y tocar secuencias en vivo con Ableton Live, sin pasar media hora
volcando stems a mano por cada canción.

Parte de la familia **Sonar**: SonarMaster es para practicar; SonarStage, para el escenario.

## Qué hace

- **Importa** paquetes de stems (ZIP/RAR, WAV/MP3) y detecta tempo, compases,
  secciones y tono a partir del click y la guía.
- **Prepara** cada canción una sola vez: mezcla, normaliza el volumen entre
  canciones, cambia de tono y separa lo que toca la banda en vivo.
- **Genera el show** de la semana en segundos, listo para Ableton Live 12.
- **Controla el show** por voz: repetir el coro, saltar secciones, extender partes.
- **Sincroniza los cifrados** en el modo show de SonarMaster.

## Estructura

| Carpeta | Contenido |
|---|---|
| `app/` | App de escritorio para Mac |
| `importer/` | Análisis e impresión de audio (Python) |
| `bridge/` | SonarStage Link: Remote Script para Ableton |
| `shared/` | Formatos compartidos (`cancion.schema.json`) |
| `docs/` | Arquitectura, convención de pistas, referencias y roadmap |

Empieza por [`docs/arquitectura.md`](docs/arquitectura.md).

## Estado

En diseño. Fase actual: **1 — Importador** (ver [`docs/roadmap.md`](docs/roadmap.md)).
