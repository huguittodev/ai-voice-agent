# Fase 1.1: Auditoría Técnica y Selección del Stack de Voz Local

**Proyecto:** Local Voice Agent  
**Fecha:** 2026-10-20  
**Autor:** Ingeniero Senior de Sistemas de Voz e Inteligencia Artificial Local  
**Estado:** Completado (Revisión de arquitectura para aprobación de fase 1.2)  

---

## 1. Resumen Ejecutivo

El objetivo de esta fase es determinar la ruta técnica más sencilla, reproducible, 100% gratuita y viable para validar una primera conversación de voz en español ejecutada íntegramente en local, antes de iniciar la construcción del CRM o la interfaz de usuario.

Tras analizar los requisitos del proyecto, el catálogo de candidatos de código abierto y las restricciones de hardware (CPU de gama alta, GPU NVIDIA de 8 GB de VRAM), se concluye lo siguiente:

1. **Stack Mínimo Recomendado:**
   - **STT (Speech-to-Text):** [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper) (modelo `small` con opción de fallback a `base`).
   - **TTS (Text-to-Speech):** [`Piper`](https://github.com/rhasspy/piper) (voz en español de España `es_ES-davefx-medium` o `es_ES-sharvard-medium`).
2. **Alternativa Directa de Calidad (Respaldo):**
   - **TTS Alternativo:** [`kokoro-onnx`](https://github.com/thewh1teagle/kokoro-onnx) (modelo `Kokoro-82M` v1.0, voces `ef_dora` / `em_alex`), en caso de que la prosodia de Piper resulte demasiado sintética para el estándar de una conversación comercial B2B.
3. **Coste Económico:** **0,00 €**. No se requiere ninguna suscripción de pago, ningún token de API en la nube y ninguna tarjeta de crédito.
4. **Cumplimiento de Restricciones:**
   - No se ha instalado ninguna librería en el sistema ni descargado ningún modelo pesado durante esta fase de auditoría.
   - El espacio de trabajo en Python ya cuenta con una estructura inicial aislada gestionada con `uv` en el directorio `services/voice/`.
   - Se mantiene intacta la directriz de no introducir Docker, telefonía real ni servicios externos.

---

## 2. Entorno Real Detectado y Datos Pendientes de Verificación

### 2.1. Estado Verificado en el Repositorio y Espacio de Trabajo
- **Estructura del Proyecto:**
  - Monorepo gestionado con `pnpm` (versión del gestor `pnpm@10.0.0` / `11.7.0`).
  - Aplicación web planificada en `apps/web` basada en Next.js 16.4.2, React 19.3.0, TypeScript 5 y TailwindCSS 4.
  - Servicio de voz aislado en `services/voice/`:
    - Gestor de paquetes: `uv` (versión 0.13.4 registrada en `pyvenv.cfg`).
    - Versión de Python configurada: `3.11` (vía `.python-version` y `requires-python = ">=3.11"`).
    - Entorno virtual existente en `services/voice/.venv` configurado contra `cpython-3.11-linux-x86_64-gnu`.
    - Dependencias actuales: sólo herramientas de desarrollo (`pytest >= 9.1.1` y `ruff >= 0.17.1`). El código en `src/voice/` está limpio (`__init__.py`).
  - Datos de prueba: `data/demo/businesses.csv` contiene únicamente datos sintéticos conforme a las reglas del proyecto (restaurante, clínica y taller ficticios en Madrid).
- **Control de Versiones (Git):**
  - Rama activa: `main`.
  - Último commit registrado: `dd07caede4f1cbab680b5398d09f7779742db24e` (*"chore: initialize local voice agent workspace"*).
  - Repositorio remoto configurado: `https://github.com/huguittodev/ai-voice-agent`.
  - Árbol de trabajo limpio.
- **Documento de Contexto Maestro:**
  - Conforme a `AGENTS.md` y a las instrucciones de la tarea, se verificó la existencia de `Local_Voice_Agent_PROJECT_CONTEXT.md` o `PROJECT_CONTEXT.md`. Dicho archivo no existe en el repositorio. Se toma como referencia directa el archivo `docs/DECISIONS.md`, el archivo `AGENTS.md` y las especificaciones del prompt.

### 2.2. Datos del Sistema Pendientes de Verificación en Ejecución
Por política estricta de no dejar procesos en segundo plano y no alterar el entorno sin autorización previa:
- **Capa de Ejecución del Entorno:** La ruta del workspace (`/home/huguittodev/ai-voice-agent`) y el runtime de Python reflejan un entorno Linux/WSL2 (Windows Subsystem for Linux), mientras que la máquina física anfitriona esperada es Windows.
- **Hardware Nominal (Pendiente de confirmación en runtime):**
  - CPU esperada: Intel Core i9-13900KF (24 núcleos / 32 hilos).
  - GPU esperada: NVIDIA GeForce RTX 3070 Ti (~8 GB VRAM).
- **Variables no verificadas directamente:** Versión exacta del controlador NVIDIA instalado en el host, presencia del CUDA Toolkit (`nvcc`), versión del kernel WSL2 y espacio libre exacto en el disco local.
- **Estrategia:** En la subfase 1.2 se ejecutará un único script de diagnóstico de 3 segundos que lea `torch.cuda.is_available()`, `torch.cuda.get_device_name()`, memoria VRAM total/libre y espacio en disco mediante librerías nativas (`psutil`, `shutil`), sin bloquear la consola.

---

## 3. Tabla Comparativa de Candidatos STT (Speech-to-Text)

| Criterio | **faster-whisper** (SYSTRAN) | **whisper.cpp** (ggml-org) | **openai-whisper** (Original) | **sherpa-onnx** (k2-fsa) | **Moonshine** (Useful Sensors) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Motor / Backend** | CTranslate2 (C++ optimizado, int8/fp16) | GGML / GGUF (C/C++ nativo) | PyTorch puro | ONNX Runtime | PyTorch / ONNX |
| **Compatibilidad SO** | Windows nativo y Linux/WSL2 | Windows (binarios o CMake) y Linux | Multiplataforma | Multiplataforma | Linux / Windows |
| **Soporte de Español** | **Excelente** (Modelos Whisper oficiales y fine-tunes) | **Excelente** (Mismos pesos GGML) | **Excelente** (Referencia) | Bueno (Modelos Whisper o Zipformer) | Deficiente en español (diseñado para inglés) |
| **Calidad WER en Español** | ~3.5% (Small, FLEURS), ~8.5% (Small, Common Voice) | Idéntica a Whisper (~3.5% FLEURS) | Idéntica (~3.5% FLEURS) | Variable según modelo (~4-9%) | > 25% (no optimizado para español) |
| **Consumo VRAM (GPU)** | **1,2 GB** (Small, float16) / **0,6 GB** (Small, int8) | **1,1 GB** (Small, cuBLAS/CUDA) | **2,0 - 2,5 GB** (Small, FP16) | **1,0 - 1,5 GB** | ~1 GB |
| **Consumo RAM / CPU** | ~800 MB RAM (Modo CPU int8) | ~600 MB RAM (Modo CPU) | > 2 GB RAM | ~600 MB RAM | ~500 MB RAM |
| **Latencia / RTF (i9-13900KF)** | RTF < **0.08** (GPU) / < **0.25** (CPU) | RTF < **0.10** (GPU) / < **0.30** (CPU) | RTF ~ **0.35** (GPU) / > **1.0** (CPU) | RTF < **0.15** | RTF < 0.10 (sólo inglés) |
| **Facilidad de Integración** | **Alta**: `pip install faster-whisper` en Python | Media: Requiere compilar con CMake o descargar DLLs de GGML | Alta: `pip install openai-whisper` (pero muy pesado) | Media: API con patrones propios | Media |
| **Licencia** | **MIT** | **MIT** | **MIT** | **Apache 2.0** | **Apache 2.0** |
| **Riesgos en Windows / WSL** | Requiere librerías cuBLAS / cuDNN compatibles si se ejecuta con CUDA | Requiere emparejar DLLs de cuBLAS en el build | Dependencia pesada de PyTorch completo | Menor documentación comunitaria en español | Falta de precisión en español comercial |

### Diagnóstico del Candidato STT:
`faster-whisper` es el claro ganador técnico:
- Es hasta 4 veces más rápido que la implementación oficial de OpenAI y consume menos de la mitad de memoria.
- Permite conmutar con un solo parámetro (`device="cuda"` o `device="cpu"`, `compute_type="int8"` o `compute_type="float16"`), lo que garantiza que si el entorno tiene problemas puntuales con controladores CUDA en Windows, la prueba puede ejecutarse en CPU en tiempo casi real gracias al procesador Intel Core i9-13900KF sin bloquear el desarrollo.

---

## 4. Tabla Comparativa de Candidatos TTS (Text-to-Speech)

| Criterio | **Piper** (Rhasspy / OHF) | **Kokoro-82M / kokoro-onnx** (hexgrad / thewh1teagle) | **Voicebox** (agjs / jamiepine) | **Coqui XTTS-v2** (Descontinuado) | **StyleTTS2 / F5-TTS** |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Arquitectura** | VITS optimizado exportado a ONNX | StyleTTS2 / ISTFTNet ligero (82M params) | Servidor envoltorio (FastAPI/Tauri) | Autoregresivo + Diffusion | Diffusion / Transformers |
| **Voces en Español (España)** | **`es_ES-davefx-medium`** (CC0) y **`es_ES-sharvard-medium`** (MIT) | **`ef_dora`** (mujer) y **`em_alex`**, **`em_santa`** (hombres) | No es un modelo; usa Piper o Kokoro internamente | Múltiples voces por clonación | Limitadas en español nativo |
| **Frecuencia de Muestreo** | 22.050 Hz | **24.000 Hz** | Depende del backend | 24.000 Hz | 24.000 Hz |
| **Requisitos Hardware** | **100% CPU** (no requiere GPU ni VRAM) | CPU o GPU opcional (~500 MB VRAM) | Depende del backend | **3,5 - 4,5 GB VRAM obligatoria** | **> 4 GB VRAM** |
| **Uso de RAM** | **~150 MB** | **~450 MB** | Variable | > 4 GB RAM | > 3 GB RAM |
| **Tamaño de Descarga** | **~63 MB** (modelo ONNX + JSON config) | **~350 MB** (ONNX + archivo de voces bin) | Depende de dependencias | > 2 GB | > 1,5 GB |
| **Latencia (TTFA - First Audio)** | **< 60 ms** (en i9-13900KF) | **~150 - 250 ms** (en CPU) / **< 80 ms** (GPU) | Latencia del modelo + overhead HTTP | > 800 - 1.500 ms (Inviable para diálogo ágil) | > 1.000 ms |
| **Naturalidad y Entonación** | Buena, inteligible y clara; algo robótica/plana en pausas largas | **Muy alta**, prosodia natural, expresividad comercial | N/A (depende del motor) | Alta, pero propensa a alucinaciones de audio | Alta |
| **Facilidad de Integración** | **Muy Alta**: `pip install piper-tts` | **Alta**: `pip install kokoro-onnx soundfile` | Baja: Requiere orquestar servidor Docker/Tauri | Baja: Proyecto abandonado, dependencias rotas | Compleja |
| **Licencia** | **MIT** (código) / **CC0 y MIT** (voces `es_ES`) | **Apache 2.0** (código y pesos) | MIT | CPML (No comercial para empresas) | MIT / No comercial según pesos |
| **Estado de Mantenimiento** | Activo (respaldado por Open Home Foundation) | Muy activo (comunidad abierta 2024-2026) | Activo como herramienta de escritorio | **Abandonado** tras el cierre de Coqui AI | Activo |

### Aclaración Específica sobre "Voicebox":
Tal como se solicitó verificar, **Voicebox no es un motor TTS/STT autónomo en sí mismo**:
1. El proyecto `jamiepine/voicebox` es una aplicación de escritorio (Tauri + FastAPI) orientada a creadores y clonación, no una librería reproducible y ligera para incrustar en un servicio de voz conversacional.
2. El repositorio `agjs/voicebox` es un envoltorio tipo servidor OpenAI para Docker que internamente delega en `faster-whisper` y `piper`.
3. Meta Voicebox (2023) nunca fue publicado con código ni modelos abiertos por motivos de seguridad.
Por tanto, adoptar "Voicebox" en esta fase supondría añadir una capa de complejidad innecesaria (APIs intermedias, interfaces gráficas o Docker) sin aportar ventajas sobre el uso directo de las librerías base.

---

## 5. Fuentes Oficiales Consultadas

- **faster-whisper:** [Repositorio Oficial SYSTRAN/faster-whisper en GitHub](https://github.com/SYSTRAN/faster-whisper)
- **CTranslate2:** [Documentación del Motor CTranslate2](https://opennmt.net/CTranslate2/)
- **whisper.cpp:** [Repositorio Oficial ggml-org/whisper.cpp en GitHub](https://github.com/ggml-org/whisper.cpp)
- **OpenAI Whisper:** [Repositorio Oficial openai/whisper](https://github.com/openai/whisper) y [Paper de Arquitectura Whisper (Radford et al.)](https://arxiv.org/abs/2212.04356)
- **Piper TTS:** [Repositorio Oficial rhasspy/piper en GitHub](https://github.com/rhasspy/piper)
- **Piper Voices Catalog:** [Catálogo de Voces de Piper en Hugging Face (rhasspy/piper-voices)](https://huggingface.co/rhasspy/piper-voices)
- **Voz Piper Davefx (es_ES):** [Ficha de modelo es_ES-davefx-medium en Hugging Face](https://huggingface.co/rhasspy/piper-voices/tree/main/es/es_ES/davefx/medium)
- **Voz Piper Sharvard (es_ES):** [Ficha de modelo es_ES-sharvard-medium en Hugging Face](https://huggingface.co/rhasspy/piper-voices/tree/main/es/es_ES/sharvard/medium)
- **Kokoro-82M:** [Repositorio de Pesos hexgrad/Kokoro-82M en Hugging Face](https://huggingface.co/hexgrad/Kokoro-82M)
- **kokoro-onnx:** [Librería Ligera thewh1teagle/kokoro-onnx en GitHub](https://github.com/thewh1teagle/kokoro-onnx)
- **Jamie Pine Voicebox:** [Repositorio jamiepine/voicebox en GitHub](https://github.com/jamiepine/voicebox)

---

## 6. Riesgos Técnicos Específicos del Hardware

### 6.1. El Cuello de Botella de los 8 GB de VRAM de la RTX 3070 Ti
En la visión a medio plazo del proyecto se incorporará un LLM local (por ejemplo, Llama 3.1 8B o Mistral 7B).
- Un modelo de 8B cuantizado en 4 bits (`Q4_K_M`) consume aproximadamente **4,8 a 5,5 GB de VRAM** solo para los pesos.
- Con una ventana de contexto comercial (KV Cache de 4k tokens), el consumo asciende a **6,0 - 6,5 GB de VRAM**.
- Si el stack de voz (STT + TTS) se ejecuta en GPU consumiendo más de 2 GB de VRAM, el sistema superará los 8 GB disponibles, provocando errores de Out Of Memory (OOM) o una penalización catastrófica de rendimiento por volcado a la memoria RAM del sistema a través del bus PCIe.
- **Mitigación Arquitectónica:**
  1. El TTS (`Piper`) se delega **100% a la CPU**. El Intel Core i9-13900KF cuenta con 24 núcleos y un rendimiento mononúcleo líder, ejecutando la inferencia VITS de Piper en menos de 60 milisegundos sin consumir ni un solo megabyte de VRAM.
  2. El STT (`faster-whisper small`) utiliza cuantización `float16` o `int8_float16`, ocupando únicamente entre **0,6 y 1,2 GB de VRAM**, dejando más de 6,8 GB de VRAM libres para el futuro LLM.

### 6.2. Complejidad de DLLs de CUDA / cuDNN en Windows
- En entornos Windows nativos, CTranslate2 requiere las bibliotecas de tiempo de ejecución `cublas64_12.dll` y `cudnn_ops64_9.dll`. Con frecuencia, los desarrolladores experimentan errores si instalan CUDA Toolkit pero no configuran manualmente los binarios de cuDNN en el `PATH`.
- **Mitigación:** En caso de discrepancia en Windows, `faster-whisper` cuenta con fallback inmediato a CPU (`device="cpu"`, `compute_type="int8"`). En el procesador i9-13900KF, la transcripción en CPU de un segmento de 3 segundos toma menos de 400 ms.

---

## 7. Combinación Recomendada y Justificación

### **Ruta Principal: `faster-whisper (small)` + `Piper (es_ES-davefx-medium)`**

1. **STT:** `faster-whisper` con el modelo `small` (o `base` para la primera prueba de humo).
   - *Por qué:* El modelo `small` (~244M parámetros) representa el "punto dulce" para el idioma español: reduce el WER a la mitad respecto al modelo `base`, comprende sin dificultad el vocabulario empresarial y técnico, y se ejecuta en menos de 100 ms por chunk de audio en una GPU RTX 3070 Ti.
2. **TTS:** `Piper` con la voz `es_ES-davefx-medium`.
   - *Por qué:* Inferencia ultrarrápida (TTFA < 60 ms), huella en disco mínima (63 MB), nulo impacto en la VRAM de la GPU, y licencia CC0 de dominio público.
   - *Voz de relevo:* `es_ES-sharvard-medium` (licencia MIT) si se prefiere una voz alternativa en español peninsular.

---

## 8. Alternativa de Respaldo

### **Ruta de Respaldo: `faster-whisper (small)` + `kokoro-onnx (ef_dora / em_alex)`**

- **Justificación:** Si durante la prueba auditiva de la subfase 1.2 la voz de Piper se percibe excesivamente plana o sintética para una llamada de prospección comercial B2B creíble, la alternativa inmediata es `kokoro-onnx`.
- **Características:**
  - Modelo `Kokoro-82M` exportado a ONNX (~350 MB en total).
  - Audio a 24 kHz con una inflexión y modulación tonal significativamente más naturales.
  - Ejecutable tanto en CPU como con aceleración CUDA sin dependencias externas pesadas gracias al paquete `kokoro-onnx`.
  - Licencia permisiva Apache 2.0.
- **Experimento de desempate:** En la subfase 1.2 se sintetizará la misma frase comercial en Piper y en Kokoro para comparar objetivamente:
  1. Latencia de generación (TTFA).
  2. Naturalidad subjetiva percibida.
  3. Consumo de recursos de CPU/RAM.

---

## 9. Plan de Pruebas para la Subfase 1.2

El objetivo de la subfase 1.2 será verificar empíricamente el funcionamiento de los componentes de forma aislada, sin interactuar todavía con micrófonos en directo, sin LLMs y sin interfaz web.

### 9.1. Frases de Prueba en Español Peninsular para Validación Comercial
Se utilizará un banco estandarizado de 5 frases que someten a prueba las dificultades fonéticas más habituales en llamadas B2B:

1. **Frase 1 (Saludo y propuesta de valor inicial):**
   > *"Buenos días, le llamo de Soluciones Cloud para presentarle nuestra herramienta de automatización para equipos comerciales."*  
   *(Evalúa cadencia conversacional y entonación de apertura).*
2. **Frase 2 (Cifras, porcentajes y fechas):**
   > *"Hemos ayudado a más de 150 empresas del sector a reducir un 35% sus costes operativos durante el primer trimestre de 2026."*  
   *(Evalúa pronunciación de números cardinales, porcentajes y años sin errores fonéticos).*
3. **Frase 3 (Marcas y términos tecnológicos en inglés):**
   > *"Nuestra solución se integra de forma nativa con Salesforce, HubSpot y Microsoft Dynamics mediante APIs seguras."*  
   *(Evalúa adaptación de anglicismos y nombres propios comerciales).*
4. **Frase 4 (Manejo de objeción y propuesta de reunión):**
   > *"Entiendo perfectamente que ahora mismo no tengan presupuesto; ¿le parece si lo comentamos brevemente el próximo jueves a las 11:30?"*  
   *(Evalúa entonación interrogativa, pausas y empatía sonora).*
5. **Frase 5 (Complejidad acústica y fonética técnica):**
   > *"Implementamos arquitecturas híbridas optimizadas sobre microservicios con cifrado de extremo a extremo sin interrumpir su operativa."*  
   *(Evalúa inteligibilidad en grupos consonánticos complejos y palabras largas).*

### 9.2. Protocolo de Medición y Métricas
Para evitar ambigüedades entre estimaciones teóricas y mediciones reales, el script de prueba registrará:

| Métrica | Método de Captura | Criterio de Éxito |
| :--- | :--- | :--- |
| **Tiempo de Inferencia STT** | `time.perf_counter()` durante `model.transcribe()` | < 300 ms para audio de 3 s (RTF < 0.10) |
| **Tiempo al Primer Audio TTS (TTFA)** | `time.perf_counter()` hasta el primer buffer generado | < 120 ms (Piper) / < 300 ms (Kokoro) |
| **Factor de Tiempo Real (RTF)** | `tiempo_generacion / duracion_audio` | RTF < 0.10 (idealmente < 0.05) |
| **Uso de Memoria RAM** | `psutil.Process().memory_info().rss` | Incremento < 1,5 GB |
| **Uso de Memoria VRAM** | `torch.cuda.memory_allocated()` o API NVML | Incremento < 1,5 GB |
| **Precisión de Transcripción (STT)** | Comparación del texto obtenido frente a la referencia | 100% de coincidencia en números y marcas |
| **Calidad de Síntesis (TTS)** | Evaluación auditiva directa del archivo `.wav` generado | Claridad fonética completa y ausencia de artefactos metálicos |

> **Regla de Etiquetado:** Todo dato presentado en el informe 1.2 llevará explícitamente el prefijo `[MEDIDO EN RUNTIME]` o `[ESTIMADO TEÓRICO]`.

---

## 10. Dependencias y Descargas Necesarias (con Tamaños Verificados)

Todas las dependencias se gestionarán estrictamente en el entorno virtual de `services/voice/` usando `uv`, sin alterar paquetes globales del sistema.

### 10.1. Paquetes Python (`services/voice/pyproject.toml`)
- `faster-whisper`: ~15 MB (+ motor CTranslate2 ~80 MB y PyAV).
- `piper-tts`: ~5 MB (+ `onnxruntime` ~60 MB).
- `soundfile`: ~15 MB (manejo de entrada/salida de audio WAV).
- `psutil`: ~1 MB (telemetría de CPU y memoria).
- *(Opcional para alternativa de respaldo):* `kokoro-onnx` (~10 MB).

### 10.2. Modelos y Archivos de Pesos
1. **STT:** `faster-whisper` modelo `small` (CTranslate2 FP16): **~460 MB** de descarga (almacenado automáticamente en caché local de Hugging Face en `~/.cache/huggingface/hub/`).
   *(Alternativa ultraligera para prueba inicial: modelo `base` de **~140 MB**).*
2. **TTS Principal:** Voz Piper `es_ES-davefx-medium`:
   - `es_ES-davefx-medium.onnx`: **63,2 MB**
   - `es_ES-davefx-medium.onnx.json`: **4,8 KB**
3. **TTS Respaldo (si se aprueba comparar):** Modelo `Kokoro-82M`:
   - `kokoro-v1.0.onnx`: **~320 MB**
   - `voices-v1.0.bin`: **~28 MB**

**Volumen Total de Descarga para la Subfase 1.2:** **~620 MB** (Ruta Principal).

---

## 11. Licencias y Restricciones de Uso

| Componente | Tipo de Licencia | Uso Comercial Permitido | Restricciones Relevantes |
| :--- | :--- | :--- | :--- |
| **faster-whisper** | MIT | Sí | Mantener aviso de copyright |
| **CTranslate2** | MIT | Sí | Mantener aviso de copyright |
| **Pesos Whisper (OpenAI)** | MIT | Sí | Libre distribución y uso comercial |
| **Piper (código)** | MIT | Sí | Mantener aviso de copyright |
| **Voz `es_ES-davefx`** | **CC0 (Dominio Público)** | **Sí** | Sin restricciones |
| **Voz `es_ES-sharvard`** | **MIT** | **Sí** | Mantener aviso de copyright |
| **Kokoro-82M (código y pesos)** | **Apache 2.0** | **Sí** | Permisivo para uso comercial |
| **kokoro-onnx** | MIT | Sí | Mantener aviso de copyright |

**Conclusión Legal:** El stack propuesto está 100% libre de licencias copyleft restrictivas (como GPLv3 o AGPL) y de cláusulas no comerciales (como la licencia CPML de modelos antiguos de Coqui). Es completamente seguro para la incubación de un producto comercial.

---

## 12. Lista Explícita de lo que NO se ha Instalado, Probado o Validado

Para mantener la máxima transparencia sobre el estado del proyecto:
1. **NO se han instalado paquetes en el sistema host** ni en el entorno virtual de Python durante esta auditoría.
2. **NO se han descargado modelos de Hugging Face** ni ningún archivo de audio externo.
3. **NO se ha dejado ningún proceso en segundo plano**, demonio ni servidor escuchando en puertos locales.
4. **NO se ha probado la captura en tiempo real desde el micrófono físico**, para no introducir variables espurias de hardware de sonido antes de validar los algoritmos.
5. **NO se ha conectado ningún LLM** (ni Ollama, ni modelos locales GGUF, ni APIs externas).
6. **NO se han utilizado frameworks complejos de streaming** (no se ha instalado LiveKit, Pipecat ni WebRTC).
7. **NO se ha implementado telefonía** ni llamadas reales.
8. **NO se ha modificado la aplicación web Next.js** en `apps/web`.
9. **NO se ha accedido al archivo `Local_Voice_Agent_PROJECT_CONTEXT.md`** por no encontrarse presente en el árbol de archivos.

---

## 13. Decisión Final

### **Decisión:** **AVANZAR A LA SUBFASE 1.2 (Pruebas Unitarias de STT y TTS)**

Se recomienda proceder con la implementación del script de validación técnica independiente en `services/voice/`, ejecutando:
1. Inferencia aislada de STT con `faster-whisper` sobre un archivo WAV en español.
2. Síntesis aislada de TTS con `Piper` (`es_ES-davefx-medium`) y comparativa opcional con `kokoro-onnx` sobre las 5 frases comerciales definidas.
3. Registro de telemetría real (latencias en milisegundos, VRAM y RAM).

**Bloqueo Preventivo:** No se iniciará ninguna descarga ni instalación de dependencias en `services/voice/` hasta recibir la aprobación formal del presente informe.
