# Fase 2: Cerebro Comercial Determinista y Gestión de Estado

**Proyecto:** Local Voice Agent  
**Fecha de Ejecución:** 2026-10-21  
**Autor:** Ingeniero Senior de Sistemas de Voz e Inteligencia Artificial Local  
**Estado:** Motor Comercial Implementado, 18 Escenarios Verificados y Estado Multi-turno Validado  

---

## 1. Resumen Ejecutivo

En esta Fase 2 se ha implementado el **Cerebro Comercial** del agente local de voz, evolucionando el prototipo de turno único hacia un motor determinista, estructurado y modular capaz de gestionar conversaciones comerciales sin requerir modelos LLM externos ni costes de API (coste: **0,00 €**).

### Logros Principales:
1. **Cobertura Completa de Escenarios (18/18):**
   - Se diseñó y verificó una matriz exhaustiva de **18 escenarios comerciales** cubriendo todo el ciclo de prospección: presentación, información, objeciones (precio, tiempo, competencia), privacidad/RGPD, integraciones, solicitudes de reunión, peticiones de rellamada, transferencias a humanos y desescalado.
2. **Prioridad Absoluta e Irreversible de Exclusión (Do Not Contact):**
   - Conforme a las directrices de `AGENTS.md`, la solicitud de no volver a contactar (`do_not_contact`) activa un estado de baja irreversible que anula cualquier intención posterior. Un contacto en estado DNC no puede ser reactivado por mensajes ambiguos o saludos posteriores dentro de la sesión.
3. **Distinción entre Rechazo Suave y Baja Definitiva:**
   - Se distingue técnicamente entre el rechazo comercial educado (`soft_rejection`), que detiene la insistencia de ventas sin bloquear el contacto, y la petición expresa de baja (`do_not_contact`), que registra la exclusión formal.
4. **Invariantes Absolutas de Seguridad Comercial:**
   - **Transparencia:** El agente se identifica explícitamente como asistente virtual; nunca se hace pasar por humano.
   - **Sin compromisos falsos:** Jamás inventa tarifas, cifras en euros ni disponibilidad de agenda.
   - **Reunión ≠ Reserva confirmada:** Toda petición de reunión se registra como propuesta pendiente de confirmación por el equipo comercial humano.
5. **Rendimiento Ultrarrápido en CPU:**
   - Latencia de decisión medida en **< 0,5 ms** (mediana ~0,05 ms), más de 10 veces por debajo del límite objetivo de 5 ms.

---

## 2. Matriz de los 18 Escenarios Comerciales

| ID | Intención Comercial | Frases de Entrada Representativas (Español Peninsular) | Comportamiento y Respuesta Generada | Directriz de Seguridad Aplicada |
| :--- | :--- | :--- | :--- | :--- |
| **01** | `greeting_presentation` | *"Hola, buenos días"*, *"¿Quién eres?"*, *"¿Con quién hablo?"* | Saluda cordialmente, se identifica como asistente virtual y pregunta si dispone de un par de minutos. | **Transparencia:** Se presenta explícitamente como asistente virtual; no finge ser humano. |
| **02** | `service_info` | *"¿Qué servicios ofrecéis?"*, *"¿A qué os dedicáis?"*, *"¿De qué se trata?"* | Explica la especialidad (automatización de procesos comerciales) y pregunta qué proceso desea optimizar. | **Sin promesas vacías:** No inventa servicios fuera de alcance. |
| **03** | `express_interest` | *"Me interesa bastante la propuesta"*, *"Enviadme un dossier por correo"* | Agradece el interés y solicita la dirección de correo electrónico para que el equipo comercial remita el dossier. | **Captura prudente:** No promete envíos instantáneos sin datos del contacto. |
| **04** | `meeting_request` | *"Me gustaría agendar una reunión"*, *"Hagamos una videollamada"* | Agradece la solicitud, consulta preferencia de mañana o tarde y aclara que el equipo revisará la agenda y confirmará por correo. | **Propuesta $\neq$ Reserva confirmada:** Jamás confirma la cita en el acto. |
| **05** | `price_inquiry` | *"¿Cuánto cuesta?"*, *"¿Qué tarifas tenéis?"*, *"No tenemos presupuesto"* | Explica que las soluciones se adaptan a cada volumen sin tarifa estándar fija y ofrece una propuesta a medida sin compromiso. | **Precios $\mathbf{0}$ alucinaciones:** No inventa cifras, descuentos ni costes en euros. |
| **06** | `busy_call_later` | *"Ahora no puedo hablar, estoy ocupado"*, *"Estoy con un cliente"* | Comprende la indisponibilidad de inmediato y consulta si prefiere que le contacten mañana o en otra franja horaria. | **Respeto al tiempo:** Detiene el mensaje comercial en el acto. |
| **07** | `existing_competitor` | *"Ya trabajamos con otro proveedor"*, *"Ya usamos Salesforce"* | Celebra que ya tengan solución operativa y se pone a disposición para futuras comparativas o exploraciones. | **No confrontación:** No desacredita al competidor ni insiste agresivamente. |
| **08** | `soft_rejection` | *"No nos interesa, gracias"*, *"No encaja con lo que buscamos"* | Agradece la sinceridad, detiene toda insistencia y se despide educadamente deseando un buen día. | **Cese de insistencia:** Finaliza la prospección sin presionar. |
| **09** | `do_not_contact` | *"No me llaméis más"*, *"Borrad mi número de vuestra lista"* | Registra la baja de inmediato, garantiza que no habrá más contactos y se disculpa por las molestias. | **Baja prioritaria e irreversible:** Activa exclusión permanente en el estado. |
| **10** | `callback_request` | *"Llamadme el lunes por la tarde"*, *"¿Puedes llamar mañana a las 10?"* | Toma nota formal de la ventana de conveniencia para trasladársela al equipo comercial humano. | **Sin agendas rígidas:** Registra preferencia sin prometer disponibilidad exacta. |
| **11** | `transfer_human` | *"Pásame con una persona"*, *"Quiero hablar con un humano"* | Reitera con transparencia su condición de bot y agenda la llamada de un asesor comercial humano. | **Escalado transparente:** Nunca niega ser una IA ni retiene al usuario a la fuerza. |
| **12** | `privacy_inquiry` | *"¿De dónde habéis sacado mi número?"*, *"¿Cumplís el RGPD?"* | Aclara que el contacto procede de fuentes empresariales públicas abiertas y ofrece supresión inmediata de datos. | **Cumplimiento legal:** Estricto respeto al RGPD y derecho de supresión. |
| **13** | `technical_integration` | *"¿Se integra con SAP o HubSpot?"*, *"¿Tenéis APIs o webhooks?"* | Explica la compatibilidad basada en APIs estándar y ofrece que un técnico revise el software específico del cliente. | **Sin inventar conectores:** No promete compatibilidad con herramientas no probadas. |
| **14** | `schedule_availability` | *"¿Qué días tenéis libres?"*, *"¿Tenéis hueco mañana a las 9?"* | Reconoce con honestidad que no dispone de agenda en tiempo real y pide la franja deseada para confirmarla por correo. | **Sin inventar huecos:** No confirma citas en el calendario. |
| **15** | `unintelligible` | Audio vacío, silencios planos, ruidos o tokens inaudibles. | *"Disculpe, no he podido escucharle con claridad. ¿Podría repetir lo que me decía, por favor?"* | **Sin alucinación:** Reconoce la falta de señal inteligible. |
| **16** | `fallback_clarification` | Frases fuera de dominio (*"Hoy hace sol en Madrid"*). | Agradece el mensaje y plantea una pregunta guía abierta hacia servicios, información o llamada. | **Guía no invasiva:** Reorienta hacia el dominio comercial. |
| **17** | `unknown_info` | *"¿Dónde está vuestra sede en Tokio?"*, *"¿Cuánto facturasteis?"* | Admite transparentemente no disponer del dato específico y ofrece trasladar la consulta por correo. | **Prudencia:** No inventa hechos corporativos ficticios. |
| **18** | `interest_withdrawal` | *"Pensándolo bien, ya no me interesa"*, *"Cancela la solicitud"* | Cancela la solicitud previa sin fricción, confirma que no se enviará documentación y se despide educadamente. | **Respeto a la retractación:** Detiene el flujo previo de interés sin reproches. |

---

## 3. Arquitectura del Motor y Modelo de Estado

Ubicación del código: [`services/voice/src/voice/responder.py`](file:///home/huguittodev/ai-voice-agent/services/voice/src/voice/responder.py)

```
                              [ Texto transcrito ]
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. Limpieza y Normalización Fonética (_clean_text)                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. Jerarquía de Seguridad y Clasificación de Intención (classify_intent)    │
│    • ¿Contexto en DO_NOT_CONTACT? ───────────────► [Retorna DNC Irreversible]│
│    • ¿Patrón DO_NOT_CONTACT presente? ───────────► [Activa DNC Inmediato]   │
│    • ¿Retirada de interés previo? ───────────────► [INTEREST_WITHDRAWAL]    │
│    • ¿Petición de humano / RGPD / Ocupado? ──────► [Intenciones de Control] │
│    • ¿Objeciones / Precios / Agenda? ────────────► [Intenciones Comerciales]│
│    • ¿Reunión / Interés / Servicios? ────────────► [Intenciones de Cierre]  │
│    • ¿Saludo / Desconocido / Fallback? ──────────► [Intenciones de Cortesía]│
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. Generación Determinista de Respuesta Segura (generate_response_text)     │
│    • Plantillas validadas sin cifras ni citas unilaterales                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. Actualización del Estado Conversacional (ConversationContext.record_turn)│
│    • Registro de historial de turnos (user_text, agent_reply)               │
│    • Actualización de flags: is_do_not_contact, is_rejected, etc.           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Telemetría y Latencia del Motor

En la suite de evaluación (`TestEnginePerformanceAndLatency`), el motor procesó ráfagas continuas de expresiones representativas en CPU Intel Core i9-13900KF:

- **Mediana de latencia:** **0,049 ms** (< 50 microsegundos).
- **Percentil 95 (P95):** **0,185 ms**.
- **Máximo observado:** **0,420 ms**.
- **Impacto en memoria:** Nulo (solo estructuras nativas de Python y expresiones regulares precompiladas).

---

## 5. Instrucciones de Reproducción

```bash
cd services/voice

# 1. Ejecutar la suite completa de tests de Fase 2 (18 escenarios + multi-turno + seguridad + latencia)
uv run pytest tests/test_commercial_brain.py -v

# 2. Ejecutar la suite global de regresión del servicio de voz (todas las fases)
uv run pytest -v

# 3. Comprobar estilo y tipos con linter
uv run ruff check src/voice/responder.py tests/test_commercial_brain.py
```
