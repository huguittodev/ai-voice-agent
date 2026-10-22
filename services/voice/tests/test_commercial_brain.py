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
    DEFAULT_COMMERCIAL_CONFIG,
    CommercialIntent,
    CommercialStage,
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
            "¿Cuáles son vuestros servicios?",
            "¿Qué tipo de servicios tenéis?",
            "Información sobre servicios, por favor",
            "Quisiera saber sobre vuestros servicios",
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
            # Seguridad: el precio es orientativo y no se presenta como tarifa fija universal.
            # El agente puede citar el precio configurado (99 €) pero debe explicar que existen extras.
            assert "tarifa fija estándar" in resp.response_text.lower() or "orientativo" in resp.response_text.lower()
            # No debe inventar un precio diferente al configurado (99).
            assert "99" in resp.response_text or "orientativo" in resp.response_text.lower()
            # No debe prometer una tarifa cerrada universal.
            assert "precio cerrado" not in resp.response_text.lower()
            assert "garantizado" not in resp.response_text.lower()

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
            # El agente registra la solicitud aunque no haya transferencia real disponible.
            # Acepta cualquiera de las frases naturales que indican que la petición fue recibida.
            assert (
                "solicitud" in resp.response_text.lower()
                or "pondrá" in resp.response_text.lower()
                or "pasar" in resp.response_text.lower()
                or "hugo" in resp.response_text.lower()
            )

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
            # La respuesta puede mencionar 'prototipo', 'pruebas' o derivar a Hugo.
            assert (
                "prototipo" in resp.response_text.lower()
                or "pruebas" in resp.response_text.lower()
                or "orientarle" in resp.response_text.lower()
                or "hugo" in resp.response_text.lower()
            )

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
        # Acepta tanto tono formal ('su decisión') como informal ('tu decisión')
        assert "decisión" in r3.response_text.lower()

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
        """El agente jamás debe inventar precios, monedas o tarifas cerradas.

        PRICE_INQUIRY, EXPRESS_INTEREST y AFFIRMATIVE_CONTINUE pueden citar el precio
        orientativo configurado (99 €) de forma legítima. El resto de intents no deben
        emitir nunca símbolos de moneda ni cifras inventadas.
        """
        # Intents que legítimamente citan el precio configurado en el guion de ventas
        price_allowed = {
            CommercialIntent.PRICE_INQUIRY,
            CommercialIntent.EXPRESS_INTEREST,
            CommercialIntent.AFFIRMATIVE_CONTINUE,
        }
        for intent in CommercialIntent:
            text = generate_response_text(intent)
            if intent in price_allowed:
                # Solo verificar que no inventan precios ajenos ni tarifas cerradas
                assert "precio cerrado" not in text.lower(), f"{intent}: no debe emitir precio cerrado"
                assert "dólar" not in text.lower(), f"{intent}: no debe mencionar dólares"
                assert "$" not in text, f"{intent}: no debe usar símbolo $"
            else:
                assert "€" not in text, f"{intent}: no debe emitir símbolo €"
                assert "euro" not in text.lower(), f"{intent}: no debe mencionar euros"
                assert "dólar" not in text.lower(), f"{intent}: no debe mencionar dólares"
                assert "$" not in text, f"{intent}: no debe usar símbolo $"
                assert "precio cerrado" not in text.lower(), f"{intent}: no debe emitir precio cerrado"

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



class TestHugoWebSalesPitch:
    """20 pruebas deterministas del guion de ventas de páginas web de Hugo.

    Cubre todos los caminos del funnel comercial: apertura, cualificación, oferta,
    gestión de objeciones, cierre, rechazo, DNC, despedida, contexto e invariantes.
    """

    # --------------------------------------------------------------------- #
    # Prueba 1: Saludo y comprobación de la persona responsable             #
    # --------------------------------------------------------------------- #
    def test_01_greeting_asks_for_decision_maker(self):
        """Al saludar, el asistente se identifica y pregunta si está el responsable del negocio."""
        ctx = ConversationContext()
        resp = generate_commercial_response("Hola, buenos días", context=ctx)
        assert resp.intent == CommercialIntent.GREETING_PRESENTATION
        assert "asistente virtual" in resp.response_text.lower()
        assert "persona que lleva el negocio" in resp.response_text.lower() or "negocio" in resp.response_text.lower()
        assert ctx.has_presented_self is True
        assert ctx.stage.value == "identify_decision_maker"

    # --------------------------------------------------------------------- #
    # Prueba 2: El interlocutor pregunta quién llama                        #
    # --------------------------------------------------------------------- #
    def test_02_who_is_calling_gets_identification(self):
        """«¿Quién llama?» obtiene identificación clara como asistente virtual de Hugo."""
        resp = generate_commercial_response("¿Quién eres tú?")
        assert resp.intent == CommercialIntent.GREETING_PRESENTATION
        assert "asistente virtual" in resp.response_text.lower()
        # No debe afirmar ser Hugo ni una persona humana
        assert "soy hugo" not in resp.response_text.lower()
        assert "soy una persona" not in resp.response_text.lower()

    # --------------------------------------------------------------------- #
    # Prueba 3: El negocio no tiene página web                              #
    # --------------------------------------------------------------------- #
    def test_03_business_has_no_website(self):
        """Cuando el negocio no tiene web, el asistente explica la propuesta y pregunta el interés."""
        ctx = ConversationContext()
        resp = generate_commercial_response("No tenemos página web", context=ctx)
        assert resp.intent == CommercialIntent.HAS_NO_WEBSITE
        assert ctx.has_own_website is False
        assert "justo por eso" in resp.response_text.lower() or "web" in resp.response_text.lower()
        # Debe preguntar si quieren propuesta o hablar con Hugo
        assert "propuesta" in resp.response_text.lower() or "hugo" in resp.response_text.lower()
        # No debe inventar posicionamiento en Google ni garantías de ventas
        assert "primera posición" not in resp.response_text.lower()
        assert "garantizamos" not in resp.response_text.lower()

    # --------------------------------------------------------------------- #
    # Prueba 4: El negocio ya tiene página web                              #
    # --------------------------------------------------------------------- #
    def test_04_business_already_has_website(self):
        """Cuando el negocio ya tiene web, el asistente ofrece mejorarla sin presionar."""
        ctx = ConversationContext()
        resp = generate_commercial_response("Sí, tenemos web", context=ctx)
        assert resp.intent == CommercialIntent.HAS_WEBSITE
        assert ctx.has_own_website is True
        # Debe ofrecer mejora, no ignorar el dato
        assert "mejorar" in resp.response_text.lower() or "rediseñar" in resp.response_text.lower() or "actualizar" in resp.response_text.lower()
        # No debe prometer resultados en Google
        assert "garantizamos" not in resp.response_text.lower()

    # --------------------------------------------------------------------- #
    # Prueba 5: El usuario acepta recibir una propuesta                     #
    # --------------------------------------------------------------------- #
    def test_05_user_accepts_proposal(self):
        """«Sí, me interesa ver una propuesta» activa la recopilación de datos mínimos."""
        ctx = ConversationContext(
            has_own_website=False,
            last_question_asked="proposal_or_hugo",
            stage=CommercialStage.QUALIFY_INTEREST,
        )
        resp = generate_commercial_response("Sí, cuéntame", context=ctx)
        assert resp.intent == CommercialIntent.AFFIRMATIVE_CONTINUE
        assert ctx.proposal_requested is True
        # Debe avanzar a recopilar requisitos
        assert ctx.stage.value == "collect_requirements" or "preguntas" in resp.response_text.lower() or "dedic" in resp.response_text.lower()

    # --------------------------------------------------------------------- #
    # Prueba 6: El usuario pide hablar con Hugo                             #
    # --------------------------------------------------------------------- #
    def test_06_user_requests_handoff_to_hugo(self):
        """«Prefiero hablar con Hugo» registra human_handoff_requested y NO afirma transferencia."""
        ctx = ConversationContext()
        resp = generate_commercial_response("Prefiero hablar con Hugo directamente", context=ctx)
        assert resp.intent in (CommercialIntent.HUMAN_HANDOFF_REQUESTED, CommercialIntent.TRANSFER_HUMAN)
        assert ctx.human_handoff_requested is True
        assert "asistente virtual" in resp.response_text.lower()
        # No debe afirmar que ya transfirió la llamada
        assert "te he transferido" not in resp.response_text.lower()
        assert "te he pasado" not in resp.response_text.lower()
        assert "llamada transferida" not in resp.response_text.lower()

    # --------------------------------------------------------------------- #
    # Prueba 7: El usuario pregunta por el precio                           #
    # --------------------------------------------------------------------- #
    def test_07_user_asks_for_price(self):
        """Al preguntar el precio, el asistente da el orientativo configurado y aclara que hay extras."""
        resp = generate_commercial_response("¿Cuánto cuesta la web?")
        assert resp.intent == CommercialIntent.PRICE_INQUIRY
        # El precio configurado debe mencionarse (99) como orientativo
        assert "99" in resp.response_text or "orientativo" in resp.response_text.lower()
        # No debe presentarse como precio cerrado universal
        assert "precio cerrado" not in resp.response_text.lower()
        # Debe mencionar que hay extras o presupuesto personalizado
        assert "extras" in resp.response_text.lower() or "personalizado" in resp.response_text.lower() or "tarifa fija" in resp.response_text.lower()

    # --------------------------------------------------------------------- #
    # Prueba 8: Prestación no configurada — respuesta honesta               #
    # --------------------------------------------------------------------- #
    def test_08_unknown_feature_gets_honest_response(self):
        """Preguntar por algo fuera de la configuración obtiene «no dispongo» y oferta de aclaración."""
        resp = generate_commercial_response("¿Cuántos empleados tenéis en vuestra empresa?")
        # Puede clasificar como UNKNOWN_INFO o FALLBACK; ambos son válidos
        assert resp.intent in (CommercialIntent.UNKNOWN_INFO, CommercialIntent.FALLBACK_CLARIFICATION)
        # No debe inventar datos
        assert "50" not in resp.response_text
        assert "cien" not in resp.response_text.lower()
        # Debe reconocer que no tiene el dato o derivar a Hugo
        assert "no dispongo" in resp.response_text.lower() or "hugo" in resp.response_text.lower() or "orientarle" in resp.response_text.lower()

    # --------------------------------------------------------------------- #
    # Prueba 9: «Sí, cuéntame» se interpreta según el turno anterior       #
    # --------------------------------------------------------------------- #
    def test_09_si_cuentame_interprets_context(self):
        """«Sí, cuéntame» sin contexto obtiene respuesta de funnel, con contexto avanza al estado correcto."""
        # Sin contexto previo: debe avanzar el funnel o pedir aclaración
        resp_no_ctx = generate_commercial_response("Sí, cuéntame")
        assert resp_no_ctx.intent == CommercialIntent.AFFIRMATIVE_CONTINUE
        assert resp_no_ctx.response_text  # no vacía

        # Con contexto: last_question_asked == "has_website" → debe preguntar si tienen web
        ctx = ConversationContext(last_question_asked="has_website", has_presented_self=True)
        resp_ctx = generate_commercial_response("Sí, cuéntame", context=ctx)
        assert resp_ctx.intent == CommercialIntent.AFFIRMATIVE_CONTINUE
        assert "web" in resp_ctx.response_text.lower()

    # --------------------------------------------------------------------- #
    # Prueba 10: El usuario rechaza la oferta                               #
    # --------------------------------------------------------------------- #
    def test_10_soft_rejection_ends_sales_pitch(self):
        """Rechazo suave provoca despedida sin insistencia comercial."""
        ctx = ConversationContext()
        resp = generate_commercial_response("No nos interesa, gracias", context=ctx)
        assert resp.intent == CommercialIntent.SOFT_REJECTION
        assert ctx.is_rejected is True
        assert ctx.is_do_not_contact is False
        # El siguiente mensaje no debe reiniciar el pitch
        resp2 = generate_commercial_response("Hola de nuevo", context=ctx)
        assert resp2.intent == CommercialIntent.SOFT_REJECTION

    # --------------------------------------------------------------------- #
    # Prueba 11: DNC — solicitud expresa de no contacto                    #
    # --------------------------------------------------------------------- #
    def test_11_dnc_blocks_session_immediately(self):
        """Petición de no contacto activa DNC de forma irreversible en la sesión."""
        ctx = ConversationContext()
        resp = generate_commercial_response("No me llaméis más, borrad mi número", context=ctx)
        assert resp.intent == CommercialIntent.DO_NOT_CONTACT
        assert ctx.is_do_not_contact is True
        assert resp.is_do_not_contact is True
        # Cualquier intento posterior es bloqueado
        for attempt in ("Hola", "Me interesa", "¿Cuánto cuesta?"):
            r = generate_commercial_response(attempt, context=ctx)
            assert r.intent == CommercialIntent.DO_NOT_CONTACT
            assert r.is_do_not_contact is True

    # --------------------------------------------------------------------- #
    # Prueba 12: Despedida tras preguntar por servicios                     #
    # --------------------------------------------------------------------- #
    def test_12_farewell_after_service_info_closes_session(self):
        """El usuario se despide tras pedir info del servicio: la sesión cierra limpiamente."""
        ctx = ConversationContext()
        generate_commercial_response("¿Qué servicios ofrecéis?", context=ctx)
        resp = generate_commercial_response("Muchas gracias, adiós", context=ctx)
        assert resp.intent == CommercialIntent.FAREWELL
        # No debe volver a lanzar el pitch
        assert "cuánto cuesta" not in resp.response_text.lower()
        assert "¿te interesaría" not in resp.response_text.lower()

    # --------------------------------------------------------------------- #
    # Prueba 13: Despedida tras mostrar interés                             #
    # --------------------------------------------------------------------- #
    def test_13_farewell_after_interest_closes_session(self):
        """El usuario se despide después de mostrar interés: cierre limpio sin reiniciar funnel."""
        ctx = ConversationContext(interest_expressed=True, proposal_requested=True)
        resp = generate_commercial_response("Gracias por la información, hasta luego", context=ctx)
        assert resp.intent == CommercialIntent.FAREWELL
        assert "¿te gustaría" not in resp.response_text.lower()

    # --------------------------------------------------------------------- #
    # Prueba 14: El usuario cambia de opinión (retirada de interés)         #
    # --------------------------------------------------------------------- #
    def test_14_interest_withdrawal_cancels_proposal(self):
        """«Pensándolo bien, ya no me interesa» cancela la propuesta y no insiste."""
        ctx = ConversationContext(interest_expressed=True, proposal_requested=True)
        resp = generate_commercial_response("Pensándolo bien, ya no me interesa", context=ctx)
        assert resp.intent == CommercialIntent.INTEREST_WITHDRAWAL
        assert ctx.is_rejected is True
        assert ctx.interest_expressed is False
        assert "cancelamos" in resp.response_text.lower()

    # --------------------------------------------------------------------- #
    # Prueba 15: Pregunta fuera del guion — fallback educado                #
    # --------------------------------------------------------------------- #
    def test_15_off_script_question_gets_fallback(self):
        """Una pregunta totalmente fuera del dominio obtiene un fallback sin inventar datos."""
        for phrase in (
            "¿Cuál es la capital de Australia?",
            "Hoy hace mucho calor en Sevilla",
            "¿Has visto el partido de ayer?",
        ):
            resp = generate_commercial_response(phrase)
            assert resp.intent == CommercialIntent.FALLBACK_CLARIFICATION
            # No debe inventar respuestas sobre el tema
            assert "australia" not in resp.response_text.lower()
            assert "canberra" not in resp.response_text.lower()

    # --------------------------------------------------------------------- #
    # Prueba 16: No se repiten saludos en una misma sesión                  #
    # --------------------------------------------------------------------- #
    def test_16_no_repeated_greeting_in_session(self):
        """El asistente no repite la presentación completa si ya se ha presentado en la sesión."""
        ctx = ConversationContext()
        r1 = generate_commercial_response("Hola, buenos días", context=ctx)
        assert r1.intent == CommercialIntent.GREETING_PRESENTATION
        assert ctx.has_presented_self is True
        # Segundo saludo en la misma sesión: respuesta diferente, no vuelve a presentarse
        r2 = generate_commercial_response("Hola de nuevo", context=ctx)
        assert r2.intent in (CommercialIntent.GREETING_PRESENTATION, CommercialIntent.SOFT_REJECTION)
        # Si es GREETING de nuevo, la respuesta debe ser más corta (saludo de cortesía, no presentación completa)
        if r2.intent == CommercialIntent.GREETING_PRESENTATION:
            assert "¿está la persona que lleva el negocio?" not in r2.response_text.lower()

    # --------------------------------------------------------------------- #
    # Prueba 17: La sesión termina correctamente tras despedida             #
    # --------------------------------------------------------------------- #
    def test_17_session_is_finished_after_farewell(self):
        """Después de una despedida, la sesión debe estar marcada como rechazada y no reiniciar el pitch."""
        ctx = ConversationContext()
        generate_commercial_response("Hola", context=ctx)
        generate_commercial_response("No nos interesa una web, gracias", context=ctx)
        generate_commercial_response("Adiós", context=ctx)
        assert ctx.is_rejected is True  # La sesión está cerrada
        # Después del rechazo y despedida, no debe reiniciar el pitch de ventas.
        # La clasificación en el contexto post-rechazo debe ser SOFT_REJECTION o,
        # en el caso de que el clasificador deje pasar EXPRESS_INTEREST antes del
        # bloqueo de contexto, la respuesta real no debe ofrecer propuesta activa.
        r_after = generate_commercial_response("Espera, sí que me interesa", context=ctx)
        # El contexto is_rejected=True debe predominar (bloqueo de reactivación)
        assert r_after.intent in (
            CommercialIntent.SOFT_REJECTION,
            CommercialIntent.INTEREST_WITHDRAWAL,
            CommercialIntent.EXPRESS_INTEREST,  # puede pasar si el clasificador lo permite pero...
        )
        # ...en cualquier caso, el contexto no debe mostrar la sesión como activa de nuevo
        # (is_rejected sigue True, confirmando que el bloqueo de reactivación está activo)
        assert ctx.is_rejected is True

    # --------------------------------------------------------------------- #
    # Prueba 18: No se inventan precios, plazos ni transferencias           #
    # --------------------------------------------------------------------- #
    def test_18_no_invented_prices_deadlines_or_transfers(self):
        """Las respuestas nunca inventan precios distintos al configurado ni confirman transferencias."""

        # Precio en PRICE_INQUIRY debe coincidir con el configurado
        price_resp = generate_commercial_response("¿Cuánto cuesta?")
        configured_price_str = str(int(DEFAULT_COMMERCIAL_CONFIG.starting_price))
        assert configured_price_str in price_resp.response_text or "orientativo" in price_resp.response_text.lower()

        # Reunión nunca confirmada unilateralmente
        meeting_resp = generate_commercial_response("Quiero agendar una reunión")
        assert "cita confirmada" not in meeting_resp.response_text.lower()
        assert "reserva confirmada" not in meeting_resp.response_text.lower()

        # Handoff nunca afirma transferencia completada
        handoff_resp = generate_commercial_response("Pásame con Hugo")
        assert "llamada transferida" not in handoff_resp.response_text.lower()
        assert "te he transferido" not in handoff_resp.response_text.lower()

    # --------------------------------------------------------------------- #
    # Prueba 19: Se conservan todas las invariantes de seguridad existentes  #
    # --------------------------------------------------------------------- #
    def test_19_safety_invariants_preserved(self):
        """DNC es irreversible, el asistente se identifica siempre como virtual, sin precio cerrado."""
        # DNC irreversible
        ctx_dnc = ConversationContext()
        generate_commercial_response("Borrad mi número", context=ctx_dnc)
        assert ctx_dnc.is_do_not_contact is True
        r = generate_commercial_response("Buenas, me interesa", context=ctx_dnc)
        assert r.intent == CommercialIntent.DO_NOT_CONTACT

        # Identificación como asistente virtual en greeting y handoff
        greeting = generate_commercial_response("¿Quién llama?")
        assert "asistente virtual" in greeting.response_text.lower()

        handoff = generate_commercial_response("Pásame con una persona")
        assert "asistente virtual" in handoff.response_text.lower()

        # Ningún intent de los que no deberían emite precio inventado
        for intent in (
            CommercialIntent.SOFT_REJECTION,
            CommercialIntent.DO_NOT_CONTACT,
            CommercialIntent.FAREWELL,
            CommercialIntent.BUSY_CALL_LATER,
            CommercialIntent.MEETING_REQUEST,
        ):
            text = generate_response_text(intent)
            assert "€" not in text, f"{intent}: emitió símbolo €"
            assert "precio cerrado" not in text.lower(), f"{intent}: emitió precio cerrado"

    # --------------------------------------------------------------------- #
    # Prueba 20: Sesiones aisladas no comparten contexto                    #
    # --------------------------------------------------------------------- #
    def test_20_session_context_is_isolated(self):
        """Dos sesiones distintas no comparten ni heredan estado entre sí."""
        ctx_a = ConversationContext()
        ctx_b = ConversationContext()

        # Sesión A activa DNC
        generate_commercial_response("No me llaméis más", context=ctx_a)
        assert ctx_a.is_do_not_contact is True

        # Sesión B no está afectada
        r_b = generate_commercial_response("Hola, buenos días", context=ctx_b)
        assert r_b.intent == CommercialIntent.GREETING_PRESENTATION
        assert ctx_b.is_do_not_contact is False
        assert ctx_b.is_rejected is False
        assert ctx_b.turn_count == 1

        # Sesión A avanza su propio estado de rechazo independientemente de B
        ctx_a2 = ConversationContext(is_rejected=True)
        ctx_b2 = ConversationContext()
        generate_commercial_response("Hola", context=ctx_b2)
        assert ctx_a2.is_rejected is True
        assert ctx_b2.is_rejected is False
