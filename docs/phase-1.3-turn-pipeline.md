# Fase 1.3: Primer Ciclo de Conversación Local (Turno Único)

**Proyecto:** Local Voice Agent  
**Fecha de Ejecución:** 2026-10-21  
**Autor:** Ingeniero Senior de Sistemas de Voz e Inteligencia Artificial Local  
**Estado:** Prototipo de Turno Único Integrado, Validado y Medido  

---

## 1. Resumen Ejecutivo

En esta Fase 1.3 se ha construido y validado con éxito el **primer ciclo completo de conversación local de turno único (Single-Turn Pipeline)**, integrando los componentes aprobados en las fases 1.1 y 1.2:

$$\text{Audio WAV (Entrada)} \xrightarrow[\text{faster-whisper small}]{\text{STT (CPU int8)}} \text{Texto Usuario} \xrightarrow[\text{Reglas locales}]{\text{Lógica Comercial}} \text{Texto Respuesta} \xrightarrow[\text{Piper davefx}]{\text{TTS (CPU)}} \text{Audio WAV (Salida)}$$

### Logros y Conclusiones Principales:
1. **Integración Extremo a Extremo 100% Funcional:**
   - Se ha implementado un script ejecutable de demostración en [`services/voice/demo_turn.py`](file:///home/huguittodev/ai-voice-agent/services/voice/demo_turn.py) y una arquitectura modular en [`services/voice/src/voice/`](file:///home/huguittodev/ai-voice-agent/services/voice/src/voice/) (`pipeline.py` y `responder.py`).
   - Se han evaluado 4 escenarios comerciales representativos (solicitud de información, expresión de interés, petición de reunión y entrada ininteligible/silencio).
2. **Latencia Extremo a Extremo Medida (Turnaround Time):**
   - **Latencia media total de procesamiento (Warm):** **1.215,1 ms** (~1,2 segundos desde que finaliza el audio del usuario hasta que el archivo de respuesta está disponible para reproducción).
   - **Desglose de la latencia media:**
     - Transcripción STT (`faster-whisper small` en CPU `int8`): **1.038,8 ms** (~85,5% del tiempo total).
     - Decisión comercial determinista (`responder.py`): **0,22 ms** (< 1 ms).
     - Síntesis TTS y escritura WAV (`Piper davefx` en CPU): **176,1 ms** (~14,5% del tiempo total).
3. **Decisión de Producto Aplicada (Voz TTS):**
   - Conforme a la evaluación auditiva directa realizada por el usuario en la Fase 1.2, se ha fijado **`es_ES-davefx-medium` (CC0)** como la voz oficial del prototipo, preservando su configuración verificada en CPU.
4. **Cumplimiento Estricto de Reglas de Seguridad Comercial:**
   - La lógica determinista **no inventa precios, citas confirmadas ni compromisos ficticios**.
   - Toda solicitud de reunión se registra como una petición pendiente de confirmación por el equipo comercial.
   - Ante audios vacíos o ininteligibles, el agente solicita una aclaración educada sin alucinar.
5. **Cobertura de Pruebas Automatizadas:**
   - 13 pruebas automatizadas pasando con éxito en **0,03 segundos** (`tests/test_benchmarks.py` y `tests/test_pipeline.py`).

---

## 2. Arquitectura del Ciclo de Turno Único

El flujo de procesamiento implementado en [`services/voice/src/voice/pipeline.py`](file:///home/huguittodev/ai-voice-agent/services/voice/src/voice/pipeline.py) consta de tres etapas desacopladas:

```
[ Usuario (WAV entrada) ]
           │
           ▼
┌───────────────────────────────────────┐
│ 1. STT: faster-whisper small (int8)   │ ➔ Inferencia CPU (i9-13900KF)
│    beam_size=5, language='es'         │ ➔ Latencia: ~1.000 - 1.100 ms
└───────────────────────────────────────┘
           │
     Texto transcrito
           ▼
┌───────────────────────────────────────┐
│ 2. Lógica Comercial Determinista      │ ➔ Expresiones regulares y clasificación
│    (voice/responder.py)               │ ➔ Reglas de seguridad sin LLM
│                                       │ ➔ Latencia: < 1 ms
└───────────────────────────────────────┘
           │
     Texto de respuesta
           ▼
┌───────────────────────────────────────┐
│ 3. TTS: Piper (es_ES-davefx-medium)   │ ➔ Inferencia CPU ONNX Runtime (22.050 Hz)
│    voice.synthesize_wav()             │ ➔ Latencia: ~150 - 220 ms
└───────────────────────────────────────┘
           │
           ▼
[ Agente (WAV salida disponible) ]
```

---

## 3. Lógica Comercial y Reglas de Seguridad

La lógica de decisión en [`services/voice/src/voice/responder.py`](file:///home/huguittodev/ai-voice-agent/services/voice/src/voice/responder.py) clasifica la intención comercial del usuario mediante reglas deterministas sin requerir un LLM:

| Escenario / Intención | Patrón de Entrada Detectado | Comportamiento y Respuesta Generada | Directriz de Seguridad Aplicada |
| :--- | :--- | :--- | :--- |
| **1. Solicitud de información de servicios** (`service_info`) | *"¿Qué servicios ofrecéis en vuestra empresa?"* | Se identifica como asistente virtual, describe la especialidad (automatización de procesos comerciales) y pregunta qué proceso desea optimizar. | **Transparencia:** Se presenta explícitamente como asistente virtual; no inventa funcionalidades no existentes. |
| **2. Expresión de interés** (`express_interest`) | *"Me interesa bastante la propuesta, ¿podríais enviarme más información?"* | Acepta el interés y solicita la dirección de correo electrónico del interlocutor para que el equipo comercial le remita el dossier. | **Sin compromisos falsos:** No promete envíos automáticos sin datos ni inventa catálogos de precios. |
| **3. Propuesta de reunión** (`meeting_request`) | *"Me gustaría agendar una reunión o llamada con vosotros para el próximo jueves."* | Agradece la solicitud, pregunta si prefiere horario de mañana o tarde, y aclara que el equipo revisará la agenda y le confirmará la cita por correo. | **Reunión $\neq$ Reserva confirmada:** Jamás confirma la cita en el acto ni inventa huecos de calendario ficticios. |
| **4. Entrada ininteligible o silencio** (`unintelligible`) | Audio vacío, silencio plano o ruido breve (< 3 caracteres). | *"Disculpe, no he podido escucharle con claridad. ¿Podría repetir lo que me decía, por favor?"* | **Sin alucinación:** Reconoce la falta de señal y solicita aclaración directa. |
| **5. Mensaje fuera de dominio** (`fallback_clarification`) | Cualquier texto que no coincida con los patrones anteriores. | *"Gracias por su mensaje. Para poder orientarle adecuadamente, ¿le gustaría conocer nuestros servicios, recibir documentación o coordinar una llamada con nuestro equipo?"* | Guía al usuario hacia los tres caminos comerciales válidos sin asumir hechos falsos. |

---

## 4. Resultados Empíricos del Benchmark de Turno

Todas las métricas fueron obtenidas en tiempo de ejecución mediante `time.perf_counter()` y se encuentran registradas en [`services/voice/output/pipeline/turn_pipeline_results.json`](file:///home/huguittodev/ai-voice-agent/services/voice/output/pipeline/turn_pipeline_results.json).

### 4.1. Tiempos de Arranque en Frío (Cold Load)
- **Carga inicial modelo STT (`faster-whisper small`):** **1.723,16 ms**
- **Carga inicial modelo TTS (`Piper davefx`):** **796,82 ms**
- **Tiempo total de inicialización en memoria:** **2.519,98 ms** (se ejecuta una única vez al arrancar el servicio).

### 4.2. Latencias Reales por Escenario (Warm Inferences)

| Escenario Evaluado | Duración Entrada (s) | STT Latencia (ms) | Decisión Reglas (ms) | TTS Latencia (ms) | Latencia Total Turnaround (ms) | Duración Respuesta (s) | Turnaround RTF |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Caso 1: Información de Servicios** | 3,320 s | 1.051,10 ms | 0,805 ms | 220,07 ms | **1.271,98 ms** | 11,877 s | **0,3831** (~2,6x) |
| **Caso 2: Expresión de Interés** | 4,203 s | 1.085,33 ms | 0,043 ms | 182,58 ms | **1.267,96 ms** | 9,160 s | **0,3017** (~3,3x) |
| **Caso 3: Petición de Reunión** | 4,946 s | 1.137,80 ms | 0,036 ms | 210,49 ms | **1.348,32 ms** | 10,588 s | **0,2726** (~3,7x) |
| **Caso 4: Silencio / Ininteligible** | 1,500 s | 880,93 ms | 0,014 ms | 91,25 ms | **972,20 ms** | 4,795 s | **0,6481** (~1,5x) |
| **PROMEDIOS GLOBALES** | **3,492 s** | **1.038,79 ms** | **0,224 ms** | **176,10 ms** | **1.215,12 ms** | **9,105 s** | **0,3479** (~2,9x) |

### 4.3. Huella de Memoria del Proceso
- **Memoria RAM ocupada por el proceso (Python con ambos modelos activos):** **~941 - 943 MB**.
- **Consumo de VRAM:** **0 MB** atribuibles a los modelos (el monitor reporta ~1.850 MB correspondientes al servidor gráfico del anfitrión Windows; los modelos corren 100% en CPU).

---

## 5. Rutas de los Archivos Generados

Todos los archivos de audio e informes han sido generados en ubicaciones locales protegidas por `.gitignore` (`*.wav` y `output/`):

### Audios de Entrada de Prueba (Usuario simulado):
- [`services/voice/output/demo_inputs/scenario_1_service_info_input.wav`](file:///home/huguittodev/ai-voice-agent/services/voice/output/demo_inputs/scenario_1_service_info_input.wav) (3,32 s)
- [`services/voice/output/demo_inputs/scenario_2_interest_input.wav`](file:///home/huguittodev/ai-voice-agent/services/voice/output/demo_inputs/scenario_2_interest_input.wav) (4,20 s)
- [`services/voice/output/demo_inputs/scenario_3_meeting_input.wav`](file:///home/huguittodev/ai-voice-agent/services/voice/output/demo_inputs/scenario_3_meeting_input.wav) (4,95 s)
- [`services/voice/output/demo_inputs/scenario_4_unintelligible_input.wav`](file:///home/huguittodev/ai-voice-agent/services/voice/output/demo_inputs/scenario_4_unintelligible_input.wav) (1,50 s de silencio)

### Audios de Respuesta Generados (Agente simulado con Piper `davefx`):
- [`services/voice/output/pipeline/scenario_1_service_info_reply.wav`](file:///home/huguittodev/ai-voice-agent/services/voice/output/pipeline/scenario_1_service_info_reply.wav) (11,88 s)
- [`services/voice/output/pipeline/scenario_2_interest_reply.wav`](file:///home/huguittodev/ai-voice-agent/services/voice/output/pipeline/scenario_2_interest_reply.wav) (9,16 s)
- [`services/voice/output/pipeline/scenario_3_meeting_reply.wav`](file:///home/huguittodev/ai-voice-agent/services/voice/output/pipeline/scenario_3_meeting_reply.wav) (10,59 s)
- [`services/voice/output/pipeline/scenario_4_unintelligible_reply.wav`](file:///home/huguittodev/ai-voice-agent/services/voice/output/pipeline/scenario_4_unintelligible_reply.wav) (4,79 s)

### Registro Completo de Métricas:
- [`services/voice/output/pipeline/turn_pipeline_results.json`](file:///home/huguittodev/ai-voice-agent/services/voice/output/pipeline/turn_pipeline_results.json)

---

## 6. Instrucciones de Reproducción y Verificación

Desde el directorio `services/voice/`:

```bash
# Situarse en el servicio de voz
cd services/voice

# 1. Ejecutar la demostración del ciclo de turno completo (Fase 1.3)
.venv/bin/python demo_turn.py

# 2. Ejecutar la suite completa de pruebas automatizadas (13 pruebas)
.venv/bin/pytest -v
```

---

## 7. Limitaciones Técnicas del Prototipo Actual

Para evitar confusiones sobre el alcance alcanzado:
1. **Inferencia por Lote de Archivo:** El prototipo procesa archivos WAV completos y cerrados. No mide la latencia de captura por micrófono, fragmentación de audio en búferes de streaming (chunks de 200–500 ms) ni reproducción en tiempo real mediante buffers de audio concurrentes.
2. **Detección de Fin de Turno (End-of-Turn / VAD):** Actualmente el corte del turno del usuario viene delimitado por el fin del archivo WAV. En una interacción real por micrófono se requerirá un detector de actividad de voz (VAD tipo Silero) para determinar cuándo el usuario ha terminado de hablar.
3. **Cuello de Botella en CPU:** La transcripción de ~4 segundos de audio toma ~1,05 segundos en CPU. Si bien es 3 veces más rápida que el tiempo real, introduce una pausa perceptible de un segundo antes de que empiece a sonar la respuesta.
4. **Conversación Estructurada:** Las respuestas se generan mediante coincidencia de patrones y plantillas; no existe razonamiento semántico libre ni gestión de historial conversacional multi-turno.

---

## 8. Próximos Pasos (Hacia la Fase 1.4)

Una vez revisada y aprobada esta fase, el siguiente paso técnico lógico consistirá en:
1. **Explorar Aceleración CUDA para STT:** Instalar los paquetes específicos `nvidia-cublas-cu12` y `nvidia-cudnn-cu12` para habilitar `faster-whisper small` en la GPU RTX 3070 Ti, con el objetivo de recortar el tiempo de transcripción de ~1.050 ms a menos de **250 ms**.
2. **Integración con VAD / Captura Local de Micrófono:** Evaluar un mecanismo local mínimo de captura con detección de silencios para poder hablar directamente al sistema en vez de usar archivos `.wav` pregrabados.
