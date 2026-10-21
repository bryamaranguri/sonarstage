# SonarStage — contexto para Claude

SonarStage es un sistema para preparar y tocar secuencias en vivo con Ableton Live.
Lo usan Bryam (secuencias + guitarra eléctrica) y uno o dos amigos con sus bandas.
**No es un producto comercial**: se comparte en privado. Contexto de uso: iglesia
(setlists de 3–6 canciones que cambian cada semana) y bodas/eventos (10–12 canciones).

Es parte de la familia de SonarMaster (`bryamaranguri/sonarmaster`), la app web de
práctica y cifrados de Bryam. SonarMaster aporta el **modo show** con cifrados
sincronizados; SonarStage no muestra cifrados por su cuenta.

Documentación completa en `docs/`. Lee primero `docs/arquitectura.md`.

## Principios que no se negocian

1. **La estabilidad en vivo manda.** Nada que pueda cortar el audio en escenario.
   Ableton es el motor de audio; SonarStage no reproduce audio propio.
2. **Todo se prepara antes del show.** Mezcla, normalización y cambio de tono se
   *imprimen* en archivos nuevos en el importador. En Ableton los faders quedan en 0 dB.
3. **Los originales nunca se modifican.** Se guardan tal como llegaron.
4. **Instalación sin comandos.** Los usuarios son músicos: `.dmg`, arrastrar a
   Aplicaciones y un asistente. Nada de terminal, Python o Homebrew para ellos.
5. **El iPad es opcional.** Solo muestra cifrados. Nada crítico depende de él.
6. **Manos ocupadas.** El control en vivo es por voz (micrófono dinámico por una
   entrada de la interfaz) y, más adelante, pedal MIDI. Hoy nadie tiene pedal.

## Entorno de los usuarios

| Usuario | Mac | Ableton | Interfaz |
|---|---|---|---|
| Bryam | M4 Max | Live 12.4.3 Suite | 2 salidas (pronto 8) |
| Amigo | MacBook Air M1 | Live 12.0 | 6 salidas |

- Soportar **Live 12** (todos los usuarios actuales). Ableton no abre un set guardado en
  una versión posterior, ni siquiera dentro de Live 12 (un set de 12.4 no abre en 12.0).
  Por eso el generador escribe el `.als` con el formato de la versión más antigua que se
  soporte (12.0): las versiones nuevas sí abren sets de versiones anteriores.
- Nunca compartir un show guardado desde Live 12.4 con alguien en 12.0: cada usuario
  genera su propio show desde la biblioteca.
- Todos tienen **SSD externo**: la biblioteca vive ahí; el show se copia al disco interno.

## Vocabulario

- **Biblioteca**: canciones importadas y preparadas una sola vez (en el SSD externo).
- **Show**: proyecto de Ableton generado a partir de la biblioteca para una fecha
  (en el disco interno, se borra después).
- **Configuración semanal**: qué instrumentos tienen instrumentista esa semana.
- **Matriz de partes**: por canción y sección, qué stems cubre cada músico en vivo
  (p. ej. EG 1 en el verso, EG 3 en el coro). Se guarda por banda.
- **EN VIVO / SECUENCIA / CUES**: los tres grupos de pistas (ver `docs/plantilla.md`).

## Idioma

Código, nombres de archivos y comentarios técnicos en inglés. Documentación,
interfaz de usuario y mensajes al usuario en español (Perú).
