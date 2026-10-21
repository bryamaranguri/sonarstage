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
| **CUES** | Click y guía. Nunca pasan por la salida principal. | Gris / blanco |
| **EN VIVO** | Respaldo de lo que toca la banda esa semana: muteado y ya mezclado. | Azul / morado |
| **SECUENCIA** | Todo lo que suena. | Naranja / amarillo |

Reglas:

1. **La app decide el grupo de cada pista** según la configuración semanal y la
   matriz de partes. Si falta el bajista, el bajo pasa a SECUENCIA.
2. **Faders en 0 dB.** La mezcla está impresa en el audio. El fader de cada grupo
   queda como control de emergencia.
3. **Nombres limpios** sin numeración automática (`EG 2`, no `8-EG 2`).
4. **Solo se crean las pistas que usan las canciones del show.**
5. **Warp**: *Beats* para click, guía, batería y percusión; *Complex* para el resto
   (*Complex Pro* si se transpone en tiempo real).
6. Una sola frecuencia de muestreo: la de la interfaz del usuario.

## Roles disponibles

Click · Guide · Drums · Perc · Bass · EG 1–4 (y `EG en vivo` / `EG secuencia`) ·
AG · Keys · Piano · Organ · Synth · Pad · Strings · Lead Vocal · Coros / Choir ·
FX · Secuencia (premezcla) · Extra (sin clasificar)

## Ruteo por perfil

- **2 salidas**: SECUENCIA y EN VIVO → salida 1 (mono). CUES → salida 2.
- **6 / 8 salidas**: secuencia estéreo en 1/2, click y guía en salidas propias,
  grupos de stems en las restantes (a definir con cada interfaz).
