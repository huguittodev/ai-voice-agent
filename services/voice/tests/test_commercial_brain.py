"""Suite completa de pruebas automatizadas para el Cerebro Comercial (Fase 2).

Verifica exhaustivamente:
- 18 escenarios comerciales simulados con variantes idiomáticas en español peninsular.
- Transiciones multi-turno y coherencia de estado conversacional.
- Irreversibilidad y prioridad absoluta de la exclusión (DO_NOT_CONTACT).
- Detención de la insistencia ante rechazo suave (SOFT_REJECTION).
- Transparencia en la identidad virtual y prohibición de inventar precios o agendas.
- Medición de latencia de decisión en CPU (< 5 ms objetivo).
"""

import time

from voice.responder import (
    CommercialIntent,
    ConversationContext,
    generate_commercial_response,
    generate_response_text,
)


class TestCommercialScenarios:
    """Verificación de los 18 escenarios comerciales obligatorios."""

    def test_scenario_01_greeting_presentation(self):
        """Escenario 1: Saludo inicial y presentación del asistente."""
        phrases = [
            "Hola, buenos días",
            "Buenas tardes",
            "Hola, ¿quién eres?",
            "¿Quién llama?",
            "Buenas, ¿con quién hablo?",
            "Hola, ¿de parte de quién?",
        ]
        for text in phrases:
            resp = generate_commercial_response(text)
            assert resp.intent == CommercialIntent.GREETING_PRESENTATION
            assert "asistente virtual" in resp.response_text.lower()
            assert not resp.is_do_not_contact

    def test_scenario_02_service_info(self):
        """Escenario 2: Solicitud de información sobre el servicio."""
        phrases = [
            "¿Qué servicios ofrecéis en vuestra empresa?",
            "Hola, me gustaría saber a qué os dedicáis",
            "¿Cuál es vuestro producto principal?",
            "¿De qué se trata este servicio?",
            "¿Cómo funciona vuestra solución?",
            "Información sobre vuestros servicios, por favor",
        ]
        for text in phrases:
            resp = generate_commercial_response(text)
            assert resp.intent == CommercialIntent.SERVICE_INFO
            assert "asistente virtual" in resp.response_text.lower()
            assert "¿qué tipo de proceso" in resp.response_text.lower()

    def test_scenario_03_express_interest(self):
        """Escenario 3: Interés y petición de información o dossier."""
        phrases = [
            "Me interesa bastante la propuesta",
            "¿Podríais enviarme más información al respecto?",
            "Estoy interesado en recibir un catálogo con detalles",
            "Suena bien lo que me cuentas",
            "Quiero más información por favor",
            "Enviadme un correo con la información",
        ]
        for text in phrases:
            resp = generate_commercial_response(text)
            assert resp.intent == CommercialIntent.EXPRESS_INTEREST
            assert "correo electrónico" in resp.response_text.lower()
            assert resp.context.interest_expressed is True

    def test_scenario_04_meeting_request(self):
        """Escenario 4: Petición de reunión o llamada."""
        phrases = [
            "Me gustaría agendar una reunión para el próximo jueves",
            "¿Podemos concertar una videollamada para vernos?",
            "Quiero tener una llamada con vosotros",
            "Hagamos una demo de la herramienta",
            "¿Cuándo podemos hablar con calma?",
        ]
        for text in phrases:
            resp = generate_commercial_response(text)
            assert resp.intent == CommercialIntent.MEETING_REQUEST
            # Seguridad: reunión no equivale a reserva confirmada
            assert "revisará la agenda y le confirmará" in resp.response_text.lower()
            assert "reserva confirmada" not in resp.response_text.lower()
            assert resp.context.meeting_requested is True

    def test_scenario_05_price_inquiry(self):
        """Escenario 5: Pregunta por el precio u objeción presupuestaria."""
        phrases = [
            "¿Cuánto cuesta el servicio?",
            "¿Qué tarifas tenéis actualmente?",
            "¿Cuál es el precio de la suscripción?",
            "Ahora mismo no tenemos presupuesto para contratar nada",
            "Me parece que esto va a ser muy caro",
            "¿Qué coste tiene implementar esto?",
        ]
        for text in phrases:
            resp = generate_commercial_response(text)
            assert resp.intent == CommercialIntent.PRICE_INQUIRY
            # Seguridad: no inventa cifras ni precios cerrados
            assert "tarifa fija estándar" in resp.response_text.lower()
            assert "€" not in resp.response_text
            assert "euro" not in resp.response_text.lower()

    def test_scenario_06_busy_call_later(self):
        """Escenario 6: Falta de tiempo o ocupado momentáneamente."""
        phrases = [
            "Ahora no puedo hablar, estoy ocupado",
            "Estoy con un cliente en este momento",
            "Me pilláis muy mal ahora mismo",
            "Estoy en una reunión, imposible atenderte",
            "Ahora mismo imposible, estoy muy liado",
        ]
        for text in phrases:
            resp = generate_commercial_response(text)
            assert resp.intent == CommercialIntent.BUSY_CALL_LATER
            assert "mal momento" in resp.response_text.lower()
            assert not resp.is_do_not_contact

    def test_scenario_07_existing_competitor(self):
        """Escenario 7: Objeción por disponer de proveedor existente."""
        phrases = [
            "Ya trabajamos con otro proveedor para esto",
            "Ya tenemos un software similar instalado",
            "Ya usamos Salesforce y no queremos cambiar",
            "Estamos muy contentos con nuestro proveedor actual",
            "Ya lo tenemos cubierto con otra empresa",
        ]
        for text in phrases:
            resp = generate_commercial_response(text)
            assert resp.intent == CommercialIntent.EXISTING_COMPETITOR
            assert "solución" in resp.response_text.lower() or "operativa" in resp.response_text.lower()
            assert not resp.is_do_not_contact

    def test_scenario_08_soft_rejection(self):
        """Escenario 8: Rechazo comercial sin petición expresa de baja."""
        phrases = [
            "No nos interesa, gracias",
            "No nos encaja con lo que buscamos",
            "No lo vemos viable para nuestro negocio",
            "De momento no queremos nada, gracias",
            "No lo necesitamos ahora mismo",
            "Gracias pero no",
        ]
        for text in phrases:
            resp = generate_commercial_response(text)
            assert resp.intent == CommercialIntent.SOFT_REJECTION
            assert resp.context.is_rejected is True
            assert resp.is_do_not_contact is False
            assert "que tenga un buen día" in resp.response_text.lower()

    def test_scenario_09_do_not_contact(self):
        """Escenario 9: Solicitud expresa de no volver a contactar (DNC)."""
        phrases = [
            "No me llaméis más por favor",
            "Borrad mi número de vuestra base de datos",
            "No quiero recibir más llamadas comerciales",
            "Dadme de baja inmediatamente",
            "Eliminad mi contacto de vuestra lista",
            "Estoy en la lista Robinson, no me vuelvas a llamar",
            "No volváis a molestar",
            "Borrad mis datos",
            "Borrad nuestros datos",
            "No me llaméis más, aunque os diga otra cosa ahora",
            "No quiero que me llaméis",
        ]
        for text in phrases:
            resp = generate_commercial_response(text)
            assert resp.intent == CommercialIntent.DO_NOT_CONTACT
            assert resp.is_do_not_contact is True
            assert resp.context.is_do_not_contact is True
            assert "no volver a contactarle" in resp.response_text.lower()
            assert "no continuaremos" in resp.response_text.lower()

    def test_scenario_10_callback_request(self):
        """Escenario 10: Petición de rellamada en otro horario."""
        phrases = [
            "Llamadme el lunes por la tarde por favor",
            "¿Puedes llamar mañana a las 10?",
            "Mejor llámame la semana que viene",
            "Hablamos el próximo jueves con más calma",
            "Llamadme luego a las 5",
        ]
        for text in phrases:
            resp = generate_commercial_response(text)
            assert resp.intent == CommercialIntent.CALLBACK_REQUEST
            assert "tomo nota de su preferencia de horario" in resp.response_text.lower()

    def test_scenario_11_transfer_human(self):
        """Escenario 11: Petición de hablar con una persona humana."""
        phrases = [
            "Pásame con una persona",
            "Quiero hablar con un humano",
            "¿Eres un robot? Pásame con alguien real",
            "Pásame con tu responsable",
            "Quiero hablar con alguien de verdad",
        ]
        for text in phrases:
            resp = generate_commercial_response(text)
            assert resp.intent == CommercialIntent.TRANSFER_HUMAN
            assert "asistente virtual" in resp.response_text.lower()
            assert "humano" in resp.response_text.lower()

    def test_scenario_12_privacy_inquiry(self):
        """Escenario 12: Preguntas sobre privacidad y origen de los datos."""
        phrases = [
            "¿De dónde habéis sacado mi número?",
            "¿Cómo tenéis mi teléfono?",
            "¿Cuál es vuestra política de privacidad?",
            "¿Cumplís con el RGPD y protección de datos?",
            "¿Qué hacéis exactamente con mis datos?",
        ]
        for text in phrases:
            resp = generate_commercial_response(text)
            assert resp.intent == CommercialIntent.PRIVACY_INQUIRY
            assert "prototipo" in resp.response_text.lower()

    def test_scenario_13_technical_integration(self):
        """Escenario 13: Preguntas sobre integraciones técnicas y APIs."""
        phrases = [
            "¿Se integra con nuestro CRM?",
            "¿Tenéis APIs o webhooks para conectar?",
            "¿Es compatible con SAP?",
            "¿Podemos conectarlo con HubSpot y WooCommerce?",
            "¿Tenéis integración con nuestro sistema?",
        ]
        for text in phrases:
            resp = generate_commercial_response(text)
            assert resp.intent == CommercialIntent.TECHNICAL_INTEGRATION
            assert "prototipo" in resp.response_text.lower()

    def test_scenario_14_schedule_availability(self):
        """Escenario 14: Preguntas sobre disponibilidad de agenda."""
        phrases = [
            "¿Qué días tenéis libres para una cita?",
            "¿Tenéis hueco mañana por la mañana?",
            "¿Cuándo tenéis agenda libre?",
            "¿Qué horarios hay disponibles para hablar?",
            "¿Estáis disponibles el próximo viernes?",
        ]
        for text in phrases:
            resp = generate_commercial_response(text)
            assert resp.intent == CommercialIntent.SCHEDULE_AVAILABILITY
            assert "no dispongo" in resp.response_text.lower()

    def test_scenario_15_unintelligible(self):
        """Escenario 15: Silencio, ruido o transcripción vacía."""
        cases = [
            "",
            "   ",
            "[música]",
            "[ruido]",
            "[silencio]",
            "...",
            "eh",
            "a",
            "??",
        ]
        for case in cases:
            resp = generate_commercial_response(case)
            assert resp.intent == CommercialIntent.UNINTELLIGIBLE
            assert (
                "no he podido escucharle con claridad" in resp.response_text.lower()
                or "mensaje claro" in resp.response_text.lower()
            )

    def test_scenario_16_fallback_clarification(self):
        """Escenario 16: Mensaje ambiguo, incompleto o fuera de dominio."""
        phrases = [
            "Hoy hace bastante calor en Madrid",
            "El coche de mi primo es de color azul",
            "Estaba leyendo una novela histórica sobre la Edad Media",
            "Me gusta la paella de los domingos",
        ]
        for text in phrases:
            resp = generate_commercial_response(text)
            assert resp.intent == CommercialIntent.FALLBACK_CLARIFICATION
            assert "orientarle" in resp.response_text.lower()

    def test_scenario_17_unknown_info(self):
        """Escenario 17: Pregunta sobre datos que el agente desconoce."""
        phrases = [
            "¿Dónde está vuestra oficina central en Londres?",
            "¿Cuánto facturó vuestra empresa el año pasado?",
            "¿Cuántos empleados sois exactamente?",
            "¿Quién es vuestro CEO y fundador?",
        ]
        for text in phrases:
            resp = generate_commercial_response(text)
            assert resp.intent == CommercialIntent.UNKNOWN_INFO
            assert "no dispongo de ese dato específico" in resp.response_text.lower()

    def test_scenario_18_interest_withdrawal(self):
        """Escenario 18: Retirada de interés tras haberlo manifestado."""
        ctx = ConversationContext()
        # Turno 1: el usuario manifiesta interés
        resp1 = generate_commercial_response("Me interesa la propuesta, enviadme información", context=ctx)
        assert resp1.intent == CommercialIntent.EXPRESS_INTEREST
        assert ctx.interest_expressed is True

        # Turno 2: el usuario retira el interés
        withdrawal_phrases = [
            "Pensándolo bien, ya no me interesa",
            "Al final cancela la solicitud",
            "Olvídalo, mejor déjalo",
            "Me he arrepentido, no enviéis nada",
        ]
        for phrase in withdrawal_phrases:
            c = ConversationContext(interest_expressed=True)
            resp2 = generate_commercial_response(phrase, context=c)
            assert resp2.intent == CommercialIntent.INTEREST_WITHDRAWAL
            assert "cancelamos" in resp2.response_text.lower()
            assert c.interest_expressed is False
            assert c.is_rejected is True


class TestMultiTurnDialogueAndState:
    """Pruebas de diálogo multi-turno y transición de estados."""

    def test_happy_path_conversation(self):
        """Conversación fluida: Saludo -> Servicios -> Interés -> Petición reunión."""
        ctx = ConversationContext()

        # Turno 1: Saludo
        r1 = generate_commercial_response("Hola, buenos días", context=ctx)
        assert r1.intent == CommercialIntent.GREETING_PRESENTATION
        assert ctx.turn_count == 1

        # Turno 2: Pregunta por servicios
        r2 = generate_commercial_response("¿Qué hacéis exactamente?", context=ctx)
        assert r2.intent == CommercialIntent.SERVICE_INFO
        assert ctx.turn_count == 2

        # Turno 3: Muestra interés
        r3 = generate_commercial_response("Me parece interesante, enviadme un dossier", context=ctx)
        assert r3.intent == CommercialIntent.EXPRESS_INTEREST
        assert ctx.interest_expressed is True
        assert ctx.turn_count == 3

        # Turno 4: Petición de reunión
        r4 = generate_commercial_response("Quiero agendar una llamada con vosotros", context=ctx)
        assert r4.intent == CommercialIntent.MEETING_REQUEST
        assert ctx.meeting_requested is True
        assert ctx.turn_count == 4

    def test_do_not_contact_is_irreversible(self):
        """Regla de seguridad: una vez en DNC, ningún mensaje reactiva la conversación."""
        ctx = ConversationContext()

        # Turno 1: El usuario pide no ser contactado
        r1 = generate_commercial_response("No me llaméis más y borrad mi número", context=ctx)
        assert r1.intent == CommercialIntent.DO_NOT_CONTACT
        assert ctx.is_do_not_contact is True

        # Intentos de reactivación accidental posteriores
        reactivation_attempts = [
            "Hola, buenos días",
            "Pensándolo bien, me interesa mucho vuestro servicio",
            "Quiero agendar una reunión urgente",
            "¿Cuánto cuesta?",
            "El tiempo está soleado",
        ]
        for attempt in reactivation_attempts:
            r = generate_commercial_response(attempt, context=ctx)
            assert r.intent == CommercialIntent.DO_NOT_CONTACT
            assert r.is_do_not_contact is True
            assert "ya quedó registrada" in r.response_text.lower()
            assert "concluida" in r.response_text.lower()

    def test_soft_rejection_stops_commercial_push(self):
        """Rechazo suave detiene la insistencia sin bloquear el contacto en DNC."""
        ctx = ConversationContext()

        # Turno 1: Saludo
        generate_commercial_response("Buenos días", context=ctx)

        # Turno 2: Rechazo educado
        r2 = generate_commercial_response("No nos interesa por ahora, gracias", context=ctx)
        assert r2.intent == CommercialIntent.SOFT_REJECTION
        assert ctx.is_rejected is True
        assert ctx.is_do_not_contact is False
        assert "que tenga un buen día" in r2.response_text.lower()

    def test_soft_rejection_prevents_subsequent_sales_pitch(self):
        """Después de un rechazo comercial, mensajes ambiguos o saludos no reactivan el pitch de venta."""
        ctx = ConversationContext()

        # Turno 1: Saludo inicial
        generate_commercial_response("Hola, buenos días", context=ctx)

        # Turno 2: Rechazo explícito
        generate_commercial_response("No me interesa, gracias", context=ctx)
        assert ctx.is_rejected is True

        # Turno 3: Saludo casual posterior
        r3 = generate_commercial_response("Hola de nuevo", context=ctx)
        # No debe volver a GREETING_PRESENTATION (que pide minutos para vender)
        assert r3.intent == CommercialIntent.SOFT_REJECTION
        assert "respetamos su decisión" in r3.response_text.lower()

        # Turno 4: Frase ambigua
        r4 = generate_commercial_response("De acuerdo", context=ctx)
        assert r4.intent == CommercialIntent.SOFT_REJECTION
        assert "no continuar" in r4.response_text.lower()

    def test_isolated_contexts_do_not_leak_state(self):
        """Dos instancias de ConversationContext distintas mantienen estado estrictamente independiente."""
        ctx_a = ConversationContext()
        ctx_b = ConversationContext()

        # Sesión A activa DNC
        r_a = generate_commercial_response("No me llaméis más y borrad mi número", context=ctx_a)
        assert r_a.intent == CommercialIntent.DO_NOT_CONTACT
        assert ctx_a.is_do_not_contact is True

        # Sesión B inicia normalmente y no está bloqueada
        r_b = generate_commercial_response("Hola, buenos días", context=ctx_b)
        assert r_b.intent == CommercialIntent.GREETING_PRESENTATION
        assert ctx_b.is_do_not_contact is False
        assert ctx_b.is_rejected is False


class TestContradictoryAndEdgePhrases:
    """Pruebas de casos borde, negaciones contradictorias y delimitación semántica."""

    def test_contradictory_dnc_negative_case(self):
        """«No quiero dejar de recibir llamadas» no debe clasificarse erróneamente como DNC."""
        resp = generate_commercial_response("No quiero dejar de recibir llamadas")
        assert resp.intent != CommercialIntent.DO_NOT_CONTACT
        assert resp.is_do_not_contact is False

    def test_callback_with_negative_preface(self):
        """«No me interesa ahora, llamadme el lunes» debe ser CALLBACK_REQUEST, no rechazo definitivo ni DNC."""
        resp = generate_commercial_response("No me interesa ahora, llamadme el lunes")
        assert resp.intent == CommercialIntent.CALLBACK_REQUEST
        assert resp.is_do_not_contact is False

    def test_dnc_with_conflicting_clauses(self):
        """«No me llaméis más, aunque os diga otra cosa ahora» debe priorizar DNC sobre cualquier ambigüedad."""
        resp = generate_commercial_response("No me llaméis más, aunque os diga otra cosa ahora")
        assert resp.intent == CommercialIntent.DO_NOT_CONTACT
        assert resp.is_do_not_contact is True


class TestCommercialSafetyInvariants:
    """Verificación de invariantes absolutas de seguridad comercial."""

    def test_no_prices_or_currencies_ever_invented(self):
        """El agente jamás debe emitir cifras de coste, monedas ni tarifas fijas."""
        for intent in CommercialIntent:
            text = generate_response_text(intent)
            assert "€" not in text
            assert "euro" not in text.lower()
            assert "dólar" not in text.lower()
            assert "$" not in text
            assert "precio cerrado" not in text.lower()

    def test_always_identifies_as_virtual_assistant(self):
        """El agente se identifica explícitamente como virtual cuando se presenta o se indaga."""
        greeting_reply = generate_response_text(CommercialIntent.GREETING_PRESENTATION)
        assert "asistente virtual" in greeting_reply.lower()

        human_reply = generate_response_text(CommercialIntent.TRANSFER_HUMAN)
        assert "asistente virtual" in human_reply.lower()

        service_reply = generate_response_text(CommercialIntent.SERVICE_INFO)
        assert "asistente virtual" in service_reply.lower()

    def test_meeting_is_never_confirmed_unilaterally(self):
        """Una solicitud de reunión se registra siempre como propuesta y no como confirmada."""
        meeting_reply = generate_response_text(CommercialIntent.MEETING_REQUEST)
        assert "no constituye una reserva confirmada" in meeting_reply.lower() or "propuesta" in meeting_reply.lower()
        assert "cita confirmada" not in meeting_reply.lower()
        assert "reserva confirmada" not in meeting_reply.lower()

    def test_schedule_availability_never_invents_slots(self):
        """La consulta de disponibilidad reconoce la falta de agenda en tiempo real."""
        sched_reply = generate_response_text(CommercialIntent.SCHEDULE_AVAILABILITY)
        assert "no dispongo" in sched_reply.lower()

    def test_no_false_unverified_claims(self):
        """Las respuestas no deben afirmar capacidades no implementadas ni orígenes de datos falsos."""
        privacy_text = generate_response_text(CommercialIntent.PRIVACY_INQUIRY)
        assert "fuentes empresariales públicas" not in privacy_text.lower()

        tech_text = generate_response_text(CommercialIntent.TECHNICAL_INTEGRATION)
        assert "principales plataformas del mercado" not in tech_text.lower()
        assert "no dispone de integraciones" in tech_text.lower()


class TestEnginePerformanceAndLatency:
    """Medición de la latencia del motor determinista (< 5 ms objetivo)."""

    def test_decision_latency_benchmark(self):
        """Evalúa 20 iteraciones sobre 14 entradas (280 muestras) midiendo mediana, media, P95 y máximo."""
        test_inputs = [
            "Hola, buenos días",
            "¿Qué servicios ofrecéis?",
            "Me interesa recibir información",
            "Quiero agendar una reunión para el martes",
            "¿Cuánto cuesta?",
            "Ahora no puedo hablar, estoy ocupado",
            "Ya trabajamos con otro proveedor",
            "No nos interesa, gracias",
            "No me llaméis más y borrad mi número",
            "¿Se conecta con nuestro CRM?",
            "Pásame con una persona humana",
            "¿De dónde habéis sacado mis datos?",
            "Hoy hace buen tiempo en Valencia",
            "",
        ]

        latencies_ms: list[float] = []

        # Warm-up de 5 iteraciones
        for _ in range(5):
            for phrase in test_inputs:
                _ = generate_commercial_response(phrase)

        # Medición de 20 iteraciones (280 muestras)
        for _ in range(20):
            for phrase in test_inputs:
                t0 = time.perf_counter()
                _ = generate_commercial_response(phrase)
                dt_ms = (time.perf_counter() - t0) * 1000.0
                latencies_ms.append(dt_ms)

        assert len(latencies_ms) == 280

        latencies_sorted = sorted(latencies_ms)
        median_ms = latencies_sorted[len(latencies_sorted) // 2]
        avg_ms = sum(latencies_ms) / len(latencies_ms)
        p95_ms = latencies_sorted[int(len(latencies_sorted) * 0.95)]
        max_ms = max(latencies_ms)

        print(
            f"\n[Telemetría Motor Comercial] Muestras: {len(latencies_ms)} | "
            f"Mediana: {median_ms:.4f} ms | Media: {avg_ms:.4f} ms | "
            f"P95: {p95_ms:.4f} ms | Máx: {max_ms:.4f} ms",
            flush=True,
        )

        # Criterio de rendimiento: la mediana debe ser inferior a 1.0 ms (muy por debajo de 5 ms)
        assert median_ms < 1.0, f"Mediana de latencia excesiva: {median_ms:.3f} ms"
        assert p95_ms < 5.0, f"P95 de latencia excesiva: {p95_ms:.3f} ms"

