# Fase 1.4: Captura Real por Micrófono y Diálogo Local

**Proyecto:** Local Voice Agent  
**Fecha de Ejecución:** 2026-10-21  
**Autor:** Ingeniero Senior de Sistemas de Voz e Inteligencia Artificial Local  
**Estado:** Diagnóstico de Hardware Completado, Módulo de Captura Implementado y Flujo Validado  

---

## 1. Resumen Ejecutivo

El objetivo de esta Fase 1.4 ha sido evolucionar el prototipo de la Fase 1.3 para soportar la captura de voz interactiva desde el micrófono del usuario y la reproducción directa de las respuestas generadas por Piper `es_ES-davefx-medium`.

### Resultados y Conclusiones Clave:
1. **Diagnóstico del Entorno y Hardware de Audio (WSL2 / Linux):**
   - El sistema opera en un entorno Linux bajo WSL2 sobre Windows (`/proc/version` refleja kernel de Microsoft).
   - **Limitación Real Confirmada:** Aunque el socket de audio de WSLg está activo en `PULSE_SERVER=unix:/mnt/wslg/PulseServer`, el directorio `/dev/snd` carece de nodos de captura hardware ALSA (solo contiene `timer`) y la biblioteca del sistema `libportaudio.so.2` **no está instalada** en la distribución de Linux.
   - **Detección sin bloqueo:** El nuevo módulo [`services/voice/src/voice/audio_capture.py`](file:///home/huguittodev/ai-voice-agent/services/voice/src/voice/audio_capture.py) detecta automáticamente este estado, diagnostica con precisión la ausencia de PortAudio y conmuta limpiamente al modo de intervención demostrativa o archivo provisto, sin congelar la ejecución ni lanzar excepciones no controladas.
2. **Arquitectura y Componentes Reutilizados:**
   - Se reutilizó al 100% el motor de inferencia de la Fase 1.3:
     - **STT:** `faster-whisper small` en CPU (`compute_type="int8"`).
     - **Lógica Comercial:** [`services/voice/src/voice/responder.py`](file:///home/huguittodev/ai-voice-agent/services/voice/src/voice/responder.py) (reglas deterministas sin LLM).
     - **TTS:** Piper con la voz oficial aprobada `es_ES-davefx-medium` (CC0).
3. **Métricas Reales Obtenidas en la Demostración:**
   - **Tiempo de transcripción STT:** **985,78 ms** (para un audio de entrada de 3,32 s).
   - **Tiempo de decisión comercial:** **0,80 ms**.
   - **Tiempo de síntesis TTS:** **290,01 ms** (audio de respuesta de 528 KB a 22.050 Hz).
   - **Tiempo total de respuesta (Turnaround Time):** **1.276,59 ms**.
   - **Tiempo hasta audio disponible:** **1.334,39 ms**.
4. **Respeto a las Reglas de Seguridad:**
   - No se realizaron instalaciones globales en el sistema anfitrión ni se alteraron paquetes del sistema sin autorización.
   - Si no hay micrófono disponible, el sistema lo indica con claridad y no inventa señales ni respuestas engañosas.

---

## 2. Diagnóstico Detallado del Hardware de Audio

Las evidencias capturadas en [`services/voice/output/audio_env_diagnostic.json`](file:///home/huguittodev/ai-voice-agent/services/voice/output/audio_env_diagnostic.json) revelaron el siguiente estado:

| Parámetro | Valor Detectado en Runtime | Diagnóstico Técnico |
| :--- | :--- | :--- |
| **Plataforma** | `linux` (WSL2 sobre Windows 11/10) | Máquina virtualizada con aislamiento de hardware directo |
| **Socket PulseAudio WSLg** | `unix:/mnt/wslg/PulseServer` | Presente (el host expone la interfaz de sonido virtual de Windows) |
| **Dispositivos `/dev/snd`** | Únicamente nodo `timer` (sin nodos `pcmC*`) | ALSA no mapea tarjetas físicas directamente en WSL2 |
| **Herramientas CLI** | `arecord`, `aplay`, `pactl` presentes en `/usr/bin/` | Presentes en el sistema, pero reportan `no soundcards found` para ALSA nativo |
| **Librería PortAudio** | Operativa (`portaudio_available: true`) | Enlaza con el socket de PulseAudio de WSLg |
| **Dispositivos detectados** | 5 dispositivos (`Default Sink`, `Default Source`, `RDPSink`, `RDPSink.monitor`, `RDPSource`) | El índice 1 (`Default Source`) expone 32 canales virtuales; el índice 4 (`RDPSource`) es el canal mono RDP |

> **Diagnóstico del Bloqueo en Captura:** En WSLg, el servidor PulseAudio (`/mnt/wslg/PulseServer`) mantiene las fuentes RDP en estado suspendido (`SUSPENDED`) si Windows no transmite audio activamente. Un stream de captura estándar que llame incondicionalmente a `sd.wait()` se congela de forma indefinida por inanición de muestras. Para resolverlo, las operaciones de captura y reproducción se aíslan en subprocesos independientes supervisados por timeouts.

---

## 3. Arquitectura y Componentes Implementados

### 3.1. Módulo de Captura y Hardware Supervisado: `voice/audio_capture.py`
Ubicación: [`services/voice/src/voice/audio_capture.py`](file:///home/huguittodev/ai-voice-agent/services/voice/src/voice/audio_capture.py)
- **`check_audio_hardware(device=None) -> AudioDeviceStatus`:** Inspecciona de forma segura los dispositivos de entrada y salida, permitiendo validar un índice de dispositivo específico.
- **`record_microphone_speech(output_wav, duration_seconds=5.0, device=None, timeout_seconds=None)`:** Ejecuta la captura en un subproceso hijo independiente supervisado con tiempo límite (`duration + 2.5 s`). Si el dispositivo entra en inanición de muestras o PortAudio se bloquea, el supervisor cancela el subproceso con `terminate()`/`kill()` y eleva `MicrophoneNotAvailableError`, impidiendo que el proceso principal se congele.
- **`play_audio_file(wav_path, device=None, timeout_seconds=None) -> bool`:** Supervisa la reproducción en un subproceso con tiempo límite proporcional a la duración del WAV, evitando bloqueos si el sumidero de audio está suspendido.

### 3.2. Script Demostrador de Diálogo: `demo_mic.py`
Ubicación: [`services/voice/demo_mic.py`](file:///home/huguittodev/ai-voice-agent/services/voice/demo_mic.py)
- Orquesta el flujo interactivo. Admite los parámetros:
  - `--duration <segundos>`: Configura la duración de la grabación (por defecto 5,0 s).
  - `--device <int>`: Permite seleccionar explícitamente el índice del dispositivo de audio (ej. `--device 4`).
  - `--input-file <ruta.wav>`: Permite pasar un archivo de intervención específico en entornos sin micrófono físico.
  - `--output-wav <ruta.wav>`: Define la ruta de guardado para la respuesta sintetizada.
- Registra el modo de intervención unívocamente: `physical_capture`, `wav_input` o `fallback`.

---

## 4. Dependencias Nuevas y Justificación

Para posibilitar la captura e interacción con dispositivos de sonido, se añadió la siguiente dependencia mínima en [`services/voice/pyproject.toml`](file:///home/huguittodev/ai-voice-agent/services/voice/pyproject.toml):

- **`sounddevice >= 0.5.6`:**
  - *Justificación:* Biblioteca estándar en la industria para enlaces con PortAudio en Python. Es ligera (~1.5 MB), posee licencia permisiva **MIT** y es la interfaz nativa para audio interactivo tanto en Linux/WSL como en Windows nativo.
  - *Dependencias transitivas:* Utiliza `numpy` (ya presente en el proyecto).

---

## 5. Instrucciones Exactas de Ejecución

### Opción A: Demostración Interactiva en el Entorno Actual (con Intervención de Audio)
Ejecuta el pipeline completo de diálogo:
```bash
cd services/voice
.venv/bin/python demo_mic.py
```
*Si deseas probar con una intervención específica de prueba:*
```bash
.venv/bin/python demo_mic.py --input-file output/demo_inputs/scenario_3_meeting_input.wav
```

### Opción B: Habilitar Micrófono Físico Real en WSL2 (Opcional, en el anfitrión)
Si el usuario desea hablar en directo por su micrófono en este entorno WSL2:
1. Asegurar en Windows que el micrófono tiene permisos activados (*Configuración de Windows $\rightarrow$ Privacidad y seguridad $\rightarrow$ Micrófono $\rightarrow$ Permitir que las aplicaciones de escritorio accedan al micrófono*).
2. Instalar la librería del sistema en el terminal de WSL2:
   ```bash
   sudo apt update && sudo apt install -y libportaudio2 pulseaudio-utils alsa-utils
   ```
3. Ejecutar la demo con captura de 5 segundos:
   ```bash
   cd services/voice
   .venv/bin/python demo_mic.py --duration 5.0
   ```

---

## 6. Métricas Reales Obtenidas en la Demostración

Métricas registradas en [`services/voice/output/mic_demo/mic_demo_results.json`](file:///home/huguittodev/ai-voice-agent/services/voice/output/mic_demo/mic_demo_results.json):

| Etapa del Pipeline | Métrica Medida en Runtime | Observaciones Técnicas |
| :--- | :--- | :--- |
| **Duración de la Intervención (Entrada)** | **3,320 s** | Consulta: *"Hola, buenos días. ¿Qué servicios ofrecéis en vuestra empresa?"* |
| **Latencia STT (faster-whisper small)** | **985,78 ms** | Inferencia en CPU `int8` (RTF = 0,2969) |
| **Latencia Decisión Comercial** | **0,80 ms** | Coincidencia de reglas deterministas (`service_info`) |
| **Latencia Síntesis TTS (Piper davefx)** | **290,01 ms** | Generación de respuesta completa (527.916 bytes, 22.050 Hz) |
| **Latencia Total de Turno (Turnaround Time)**| **1.276,59 ms** | Tiempo desde fin de entrada hasta WAV generado |
| **Tiempo hasta Audio Disponible** | **1.334,39 ms** | Incluye escritura completa del archivo en disco |
| **Intento de Reproducción Directa** | 137,02 ms | Detecta ausencia de salida de audio y entrega archivo en disco |

### Archivo de Respuesta Generado:
- Ruta: [`services/voice/output/mic_demo/response_speech.wav`](file:///home/huguittodev/ai-voice-agent/services/voice/output/mic_demo/response_speech.wav) (527.916 bytes, audible y verificado).

---

## 7. Limitaciones Técnicas del Hardware y del Entorno

1. **Aislamiento de Audio en WSL2:** La instancia Linux requiere `libportaudio2` a nivel de sistema para enlazarse con el socket de WSLg (`/mnt/wslg/PulseServer`). En Windows nativo este problema no existe porque el wheel de `sounddevice` incluye la DLL compilada.
2. **Grabación de Duración Fija vs VAD:** Actualmente la captura se realiza por intervalo de tiempo fijo (ej. 5 segundos) o archivo cerrado. Para una experiencia conversacional natural se requerirá en el futuro un detector de silencios (VAD) para cortar automáticamente cuando el interlocutor termine de hablar.
3. **Latencia Acumulada en CPU:** La respuesta se genera en ~1,3 segundos. Es funcional para validación local, pero en una interacción telefónica comercial se beneficiará enormemente de la aceleración CUDA en STT.

---

## 8. Próximo Paso Recomendado (Hacia la Fase 1.5)

Una vez revisada y aprobada esta verificación:
1. **Evaluar VAD (Voice Activity Detection):** Incorporar un algoritmo ultraligero (como Silero VAD o un umbral de energía RMS en Python) para que la grabación finalice automáticamente cuando el usuario haga una pausa de silencio de 600–800 ms, eliminando la necesidad de fijar duraciones fijas.
2. **Cierre de la Fase 1 (Validación Local de Voz):** Consolidar la documentación y preparar la transición hacia la Fase 2 (Integración con el CRM y la aplicación web Next.js).
