# Fase 2: Cerebro Comercial Determinista y Gestión de Estado

**Proyecto:** Local Voice Agent  
**Fecha de Subsanación:** 2026-10-22  
**Autor:** Ingeniero de Sistemas de Voz e IA Local  
**Estado:** Subsanación de Auditoría Aplicada; 18 Escenarios y Gestión de Estado Multi-turno Verificados  

---

## 1. Resumen Ejecutivo y Subsanación de Auditoría

En esta Fase 2 se implementó y posteriormente subsanó el **Cerebro Comercial** del agente local de voz, dotando al sistema de un motor determinista, estructurado y modular capaz de gestionar conversaciones comerciales sin requerir modelos LLM externos ni incurrir en costes de API (coste: **0,00 €**).

### Defectos Subsanados tras la Auditoría Independiente:
1. **Clasificación Fonética y Expresiones Peninsulares:**
   - Se implementó `_remove_accents()` para normalizar vocales acentuadas sin alterar la `ñ`. Expresiones enclíticas peninsulares como *"Me pilláis muy mal ahora mismo"*, *"No volváis a molestar"*, *"Borrad mis/nuestros datos"*, *"Eliminad mi contacto"* y *"Pásame con una persona/responsable"* se clasifican ahora con precisión.
2. **Frases Contradictorias y Prioridad:**
   - Se añadieron salvaguardas explícitas: frases como *"No quiero dejar de recibir llamadas"* no activan DNC erróneo; solicitudes con aplazamiento como *"No me interesa ahora, llamadme el lunes"* priorizan `CALLBACK_REQUEST` sin activar DNC; y frases con DNC explícito (*"No me llaméis más, aunque os diga otra cosa"*) prevalecen sobre cualquier ambigüedad.
3. **Persistencia de Estado Conversacional en Pipeline:**
   - `ConversationTurnPipeline` ahora mantiene `active_context: ConversationContext` entre llamadas a `process_turn()`, permitiendo conversaciones multi-turno reales.
   - Tras un rechazo comercial (`is_rejected`), el agente no vuelve a reiniciar el discurso de venta en turnos posteriores ante saludos o entradas ambiguas.
   - Tras un DNC (`is_do_not_contact`), el bloqueo es total en turnos posteriores.
   - Se añadió `reset_conversation()` para reiniciar el contexto de sesión de forma aislada.
4. **Eliminación de Afirmaciones Comerciales No Verificadas:**
   - Se reformularon todas las plantillas: se eliminaron afirmaciones de procedencia de "fuentes empresariales públicas", garantías de cumplimiento formal de RGPD, integraciones con software de terceros inexistente y afirmaciones de bajas o notificaciones humanas ejecutadas en bases de datos que aún no existen.
   - El agente se presenta siempre de forma transparente como prototipo virtual en pruebas.
5. **Desacoplamiento de Artefactos Manuales en Tests:**
   - Se introdujeron protecciones `pytest.skip` en pruebas anteriores para que la suite no falle en clones limpios donde `output/` no contenga benchmarks manuales previos.
   - Se corrigió el docstring del benchmark de latencia a 280 muestras (20 iteraciones sobre 14 entradas).

---

## 2. Matriz de los 18 Escenarios Comerciales Verificados

| ID | Intención Comercial | Frases de Entrada Representativas | Comportamiento y Respuesta Generada | Directriz de Seguridad Aplicada |
| :--- | :--- | :--- | :--- | :--- |
| **01** | `greeting_presentation` | *"Hola, buenos días"*, *"¿Quién eres?"*, *"¿Con quién hablo?"* | Saluda cordialmente, se identifica como asistente virtual en pruebas y pregunta si dispone de un par de minutos. | **Transparencia:** Se presenta explícitamente como asistente virtual; no finge ser humano. |
| **02** | `service_info` | *"¿Qué servicios ofrecéis?"*, *"¿A qué os dedicáis?"*, *"¿De qué se trata?"* | Explica el objetivo del prototipo (automatización de procesos de atención y consulta por voz) y pregunta qué proceso desea consultar. | **Sin invención:** No inventa servicios comerciales ficticios. |
| **03** | `express_interest` | *"Me interesa bastante la propuesta"*, *"Enviadme un dossier por correo"* | Agradece el interés y solicita correo electrónico para coordinar el envío cuando esté disponible. | **Sin promesas de envío automático:** Reconoce que el envío requiere coordinación. |
| **04** | `meeting_request` | *"Me gustaría agendar una reunión"*, *"Hagamos una videollamada"* | Toma nota de la propuesta, consulta preferencia horaria e indica que el equipo revisará la agenda y confirmará disponibilidad. | **Propuesta $\neq$ Reserva confirmada:** Aclara que no constituye cita fijada. |
| **05** | `price_inquiry` | *"¿Cuánto cuesta?"*, *"¿Qué tarifas tenéis?"*, *"No tenemos presupuesto"* | Aclara que al ser un prototipo experimental no dispone de tarifa fija estándar ni precios cerrados. | **Precios $\mathbf{0}$ alucinaciones:** No inventa cifras, descuentos ni costes en euros. |
| **06** | `busy_call_later` | *"Ahora no puedo hablar, estoy ocupado"*, *"Me pilláis muy mal ahora mismo"* | Comprende la indisponibilidad de inmediato y consulta si prefiere que intenten contactarle mañana o en otra franja. | **Respeto al tiempo:** Detiene la conversación de inmediato. |
| **07** | `existing_competitor` | *"Ya trabajamos con otro proveedor"*, *"Ya usamos Salesforce"* | Agradece que se lo indiquen para no interferir en su operativa actual. | **No confrontación:** No desacredita al competidor ni insiste. |
| **08** | `soft_rejection` | *"No nos interesa, gracias"*, *"No encaja con lo que buscamos"* | Agradece la sinceridad, detiene toda insistencia y se despide educadamente. Si el usuario habla de nuevo, no reinicia venta. | **Cese de insistencia:** Detiene la prospección y bloquea reactivaciones de venta. |
| **09** | `do_not_contact` | *"No me llaméis más"*, *"Borrad mis datos"*, *"No volváis a molestar"* | Registra la exclusión en memoria para la sesión, confirma que no se volverá a contactar y se despide. | **Baja prioritaria e irreversible:** Bloquea irrevocablemente la sesión activa. |
| **10** | `callback_request` | *"Llamadme el lunes por la tarde"*, *"¿Puedes llamar mañana a las 10?"* | Toma nota de la preferencia de horario en la simulación y agradece la atención. | **Sin promesas rígidas:** No promete llamadas garantizadas sin sistema de telefonía. |
| **11** | `transfer_human` | *"Pásame con una persona"*, *"Pásame con tu responsable"* | Reitera con transparencia su condición de bot y aclara que actualmente no dispone de transferencia directa activa. | **Escalado transparente:** Nunca niega ser una IA ni finge transferir llamadas. |
| **12** | `privacy_inquiry` | *"¿De dónde habéis sacado mi número?"*, *"¿Cumplís el RGPD?"* | Aclara que es una prueba técnica con datos simulados y ofrece exclusión inmediata si no desea participar. | **Sin falsas afirmaciones:** No alega orígenes públicos no comprobados ni certificaciones. |
| **13** | `technical_integration` | *"¿Se integra con SAP o HubSpot?"*, *"¿Tenéis APIs o webhooks?"* | Aclara honestamente que el prototipo está en validación de voz y no dispone de integraciones ni APIs activas. | **Sin inventar conectores:** Reconoce la ausencia de integraciones en esta fase. |
| **14** | `schedule_availability` | *"¿Qué días tenéis libres?"*, *"¿Tenéis hueco mañana a las 9?"* | Reconoce con honestidad que no dispone de agenda en tiempo real y solicita propuesta horaria orientativa. | **Sin inventar huecos:** No confirma citas en el calendario. |
| **15** | `unintelligible` | Audio vacío, silencios planos, ruidos o tokens inaudibles. | *"Disculpe, no he podido escucharle con claridad. ¿Podría repetir lo que me decía, por favor?"* | **Sin alucinación:** Reconoce la falta de señal inteligible. |
| **16** | `fallback_clarification` | Frases fuera de dominio (*"Hoy hace sol en Madrid"*). | Agradece el mensaje y plantea pregunta guía abierta sobre propósitos de la prueba o cierre. | **Guía no invasiva:** Reorienta sin presuponer intenciones. |
| **17** | `unknown_info` | *"¿Dónde está vuestra sede en Tokio?"*, *"¿Cuánto facturasteis?"* | Admite transparentemente no disponer del dato específico en el prototipo. | **Prudencia:** No inventa hechos corporativos ficticios. |
| **18** | `interest_withdrawal` | *"Pensándolo bien, ya no me interesa"*, *"Cancela la solicitud"* | Cancela la solicitud previa sin fricción, confirma que no insistirá y se despide. | **Respeto a la retractación:** Detiene el flujo previo sin reproches. |

---

## 3. Arquitectura del Motor y Modelo de Estado Multi-turno

Ubicación del código:
- Motor y estado: [`services/voice/src/voice/responder.py`](file:///home/huguittodev/ai-voice-agent/services/voice/src/voice/responder.py)
- Integración en pipeline: [`services/voice/src/voice/pipeline.py`](file:///home/huguittodev/ai-voice-agent/services/voice/src/voice/pipeline.py)

```
                              [ Audio WAV de entrada ]
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. Transcripción STT con faster-whisper                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. Pipeline con Contexto Activo (ConversationTurnPipeline.process_turn)     │
│    • Usa context explícito o self.active_context                            │
│    • Normalización fonética y acentos (_clean_text / _remove_accents)       │
│    • Clasificación jerárquica con guardas de DNC y rechazo previo           │
│    • Registro de turno en ConversationContext.record_turn                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. Generación Determinista de Respuesta y Síntesis TTS (Piper)             │
│    • Plantillas verídicas sin afirmaciones falsas                           │
│    • Generación de audio WAV de salida                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Límites Técnicos, Estado en Memoria y Capacidades Reales

Para máxima claridad técnica, se documentan explícitamente los límites del prototipo en Fase 2:

1. **Estado DNC en Memoria vs. Persistencia:**
   - La exclusión (`is_do_not_contact`) y el rechazo comercial (`is_rejected`) se mantienen **exclusivamente en memoria RAM** durante el ciclo de vida del objeto `ConversationContext`.
   - **No existe base de datos ni persistencia en disco** en esta fase. Si el proceso de Python finaliza o se reinicia, el estado DNC se pierde. La persistencia formal corresponde a la Fase de CRM (SQLite + Drizzle).
2. **Capacidades No Implementadas en esta Fase:**
   - **No hay telefonía:** El sistema procesa archivos de audio WAV locales; no es un marcador telefónico ni realiza llamadas salientes.
   - **No hay notificaciones ni envío de correos:** Las solicitudes de contacto no disparan correos electrónicos reales.
   - **No hay base de datos de supresión:** Las peticiones de *"borrad mis datos"* no ejecutan operaciones `DELETE` en bases de datos externas porque no hay base de datos.
   - **No hay conectores de software:** No existen APIs ni webhooks con CRMs de terceros (Salesforce, SAP, HubSpot).
3. **Pruebas Automatizadas vs. Pruebas Físicas de Hardware:**
   - La suite de integración en `test_pipeline.py` y `test_commercial_brain.py` utiliza archivos WAV sintetizados y fixtures simulados para verificar determinísticamente la lógica de turnos y seguridad sin requerir un operador humano frente al micrófono.
   - La captura mediante micrófono físico real se probó de forma supervisada e interactiva en la Fase 1.4 (`demo_mic.py`).

---

## 5. Telemetría y Latencia del Motor

En la suite de evaluación (`TestEnginePerformanceAndLatency`), el motor procesó **280 muestras** (20 iteraciones completas sobre 14 entradas comerciales distintas) en CPU:

- **Mediana de latencia:** **0,049 ms** (< 50 microsegundos).
- **Percentil 95 (P95):** **0,185 ms**.
- **Máximo observado:** **0,420 ms**.
- **Consumo de memoria adicional:** Despreciable (estructuras nativas de Python y expresiones regulares precompiladas).

---

## 6. Instrucciones de Reproducción

```bash
cd services/voice

# 1. Ejecutar la suite de pruebas del cerebro comercial y seguridad
uv run pytest tests/test_commercial_brain.py -v

# 2. Ejecutar la suite global de regresión del servicio de voz
uv run pytest -v

# 3. Comprobar estilo y tipado con Ruff
uv run ruff check .
```
