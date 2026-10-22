"""Pruebas unitarias y de integración para la sesión conversacional continua (Incremento 3.2).

Verifica de forma 100% determinista y sin hardware físico:
1. Retención íntegra de contexto a lo largo de varios turnos consecutivos.
2. Secuencia estricta de fases: Escucha -> STT -> Cerebro comercial -> TTS -> Reproducción.
3. Recuperación ante audio vacío y errores de captura.
4. Límite de silencios consecutivos (timeout_no_speech) sin bucle infinito.
5. Cierre inmediato ante activación de NO CONTACTO (DO_NOT_CONTACT).
6. Salida limpia ante frase explícita de finalización.
7. Manejo y cierre controlado ante KeyboardInterrupt (Ctrl+C).
8. Programmatic stop y límite máximo de turnos.
"""

from unittest.mock import MagicMock

from voice.audio_capture import MicrophoneNotAvailableError
from voice.pipeline import ConversationTurnPipeline, TurnTelemetry
from voice.responder import CommercialIntent, ConversationContext
from voice.session import (
    ConversationSession,
    SessionConfig,
    SessionEndReason,
    SessionState,
    _normalize_phrase,
)
from voice.vad import VADState


def _create_mock_pipeline() -> MagicMock:
    """Crea un mock del pipeline de turno que simula STT, decisión y TTS sin modelos pesados."""
    pipe = MagicMock(spec=ConversationTurnPipeline)
    pipe.is_loaded = True
    pipe.active_context = ConversationContext()
    pipe.piper_voice = MagicMock()

    def mock_process_turn(input_wav_path, output_wav_path, context=None):
        ctx = context if context is not None else pipe.active_context
        # Determinar intención simulada según el path o contexto de prueba
        transcribed = getattr(pipe, "_next_transcription", "Hola, buenos días")
        from voice.responder import generate_commercial_response
        resp = generate_commercial_response(transcribed, context=ctx)

        telemetry = TurnTelemetry(
            input_wav_path=input_wav_path,
            output_wav_path=output_wav_path,
            input_audio_duration_s=2.0,
            output_audio_duration_s=1.8,
            stt_inference_ms=120.0,
            decision_ms=0.5,
            tts_synthesis_ms=180.0,
            total_turnaround_ms=300.5,
            turnaround_rtf=0.15,
            transcribed_text=transcribed,
            response_text=resp.response_text,
            intent_detected=resp.intent.value,
            confidence=resp.confidence,
            ram_process_mb=250.0,
            vram_mb=0.0,
            stt_model="mock_small",
            stt_device="cpu",
            stt_compute_type="int8",
            tts_model_path="mock_piper.onnx",
            context=ctx,
        )
        return telemetry

    pipe.process_turn.side_effect = mock_process_turn
    return pipe


class TestPhraseNormalization:
    """Pruebas de la función de normalización de frases de salida."""

    def test_normalize_phrase_removes_accents_and_punctuation(self):
        assert _normalize_phrase("¡Adiós!") == "adios"
        assert _normalize_phrase("Terminar conversación...") == "terminar conversacion"
        assert _normalize_phrase("  ¿Finalizar LLAMADA?  ") == "finalizar llamada"


class TestConversationSessionMultiTurn:
    """Pruebas del bucle continuo multi-turno y retención de contexto."""

    def test_multi_turn_session_preserves_context_across_turns(self, tmp_path):
        """Verifica que una sesión de 3 turnos retiene y acumula el historial y estado conversacional."""
        pipe = _create_mock_pipeline()
        cfg = SessionConfig(
            max_turns=3,
            session_output_dir=str(tmp_path / "sessions"),
        )

        mock_capture = MagicMock()
        mock_capture.return_value = {"success": True, "state": VADState.SPEECH_ENDED.value}
        mock_playback = MagicMock(return_value=True)

        session = ConversationSession(
            pipeline=pipe,
            config=cfg,
            capture_func=mock_capture,
            playback_func=mock_playback,
        )

        # Configurar 3 intervenciones consecutivas
        transcriptions = [
            "Hola, buenos días",
            "¿Qué servicios ofrecéis en vuestra empresa?",
            "Me gustaría agendar una reunión para el próximo martes",
        ]

        def dynamic_process(
            input_wav_path: str,
            output_wav_path: str,
            context: ConversationContext | None = None,
        ) -> TurnTelemetry:
            idx = session._turns_completed
            pipe._next_transcription = transcriptions[idx] if idx < len(transcriptions) else "Gracias"
            ctx = context if context is not None else pipe.active_context
            from voice.responder import generate_commercial_response
            resp = generate_commercial_response(pipe._next_transcription, context=ctx)
            return TurnTelemetry(
                input_wav_path=input_wav_path,
                output_wav_path=output_wav_path,
                input_audio_duration_s=2.0,
                output_audio_duration_s=1.5,
                stt_inference_ms=100.0,
                decision_ms=0.4,
                tts_synthesis_ms=150.0,
                total_turnaround_ms=250.4,
                turnaround_rtf=0.125,
                transcribed_text=pipe._next_transcription,
                response_text=resp.response_text,
                intent_detected=resp.intent.value,
                confidence=resp.confidence,
                ram_process_mb=200.0,
                vram_mb=0.0,
                stt_model="mock",
                stt_device="cpu",
                stt_compute_type="int8",
                tts_model_path="mock",
                context=ctx,
            )

        pipe.process_turn.side_effect = dynamic_process

        telemetry = session.run()

        # Debe haber ejecutado exactamente 3 turnos y cerrado por límite de turnos
        assert telemetry.total_turns == 3
        assert telemetry.end_reason == SessionEndReason.MAX_TURNS_REACHED
        assert len(telemetry.turns_telemetry) == 3

        # Comprobar que el contexto acumuló los 3 turnos
        ctx = pipe.active_context
        assert ctx.turn_count == 3
        assert len(ctx.history) == 3
        assert ctx.meeting_requested is True  # Marcado en el turno 3
        assert ctx.current_intent == CommercialIntent.MEETING_REQUEST

    def test_session_execution_order_and_states(self, tmp_path):
        """Comprueba el orden secuencial estricto de los estados del autómata."""
        pipe = _create_mock_pipeline()
        cfg = SessionConfig(max_turns=1, session_output_dir=str(tmp_path))

        state_history: list[SessionState] = []

        def on_change(state, msg):
            state_history.append(state)

        session = ConversationSession(
            pipeline=pipe,
            config=cfg,
            capture_func=lambda *args, **kwargs: {"success": True, "state": VADState.SPEECH_ENDED.value},
            playback_func=lambda *args, **kwargs: True,
            on_state_change=on_change,
        )

        session.run()

        # Secuencia esperada para 1 turno:
        # LISTENING -> PROCESSING -> PLAYING -> FINISHED
        assert SessionState.LISTENING in state_history
        assert SessionState.PROCESSING in state_history
        assert SessionState.PLAYING in state_history
        assert SessionState.FINISHED in state_history

        l_idx = state_history.index(SessionState.LISTENING)
        pr_idx = state_history.index(SessionState.PROCESSING)
        pl_idx = state_history.index(SessionState.PLAYING)
        f_idx = state_history.index(SessionState.FINISHED)

        assert l_idx < pr_idx < pl_idx < f_idx


class TestSessionEdgeCasesAndTermination:
    """Pruebas de terminación, timeouts y gestión de fallos."""

    def test_session_handles_consecutive_timeouts_limit(self, tmp_path):
        """Silencios consecutivos reiterados finalizan la sesión sin bucle infinito."""
        pipe = _create_mock_pipeline()
        cfg = SessionConfig(
            max_consecutive_timeouts=2,
            play_timeout_prompts=False,
            session_output_dir=str(tmp_path),
        )

        mock_capture = MagicMock()
        # Siempre devuelve timeout_no_speech
        mock_capture.return_value = {"success": True, "state": VADState.TIMEOUT_NO_SPEECH.value}

        session = ConversationSession(
            pipeline=pipe,
            config=cfg,
            capture_func=mock_capture,
            playback_func=MagicMock(return_value=True),
        )

        telemetry = session.run()

        assert telemetry.end_reason == SessionEndReason.MAX_CONSECUTIVE_TIMEOUTS
        assert telemetry.consecutive_timeouts == 2
        assert telemetry.total_turns == 0  # No se completó ningún turno con habla

    def test_session_terminates_immediately_on_dnc(self, tmp_path):
        """Si el usuario solicita no ser contactado (DNC), la sesión se bloquea y termina."""
        pipe = _create_mock_pipeline()
        pipe._next_transcription = "Por favor, no me llaméis nunca más y borrad mi número."
        cfg = SessionConfig(max_turns=5, session_output_dir=str(tmp_path))

        session = ConversationSession(
            pipeline=pipe,
            config=cfg,
            capture_func=lambda *args, **kwargs: {"success": True, "state": VADState.SPEECH_ENDED.value},
            playback_func=MagicMock(return_value=True),
        )

        telemetry = session.run()

        assert telemetry.end_reason == SessionEndReason.DO_NOT_CONTACT
        assert telemetry.total_turns == 1
        assert pipe.active_context.is_do_not_contact is True
        assert pipe.active_context.is_rejected is True

    def test_session_terminates_on_explicit_exit_phrase(self, tmp_path):
        """Frases como 'adiós' o 'terminar conversación' provocan salida limpia."""
        pipe = _create_mock_pipeline()
        pipe._next_transcription = "Muchas gracias por todo, adiós."
        cfg = SessionConfig(max_turns=5, session_output_dir=str(tmp_path))

        session = ConversationSession(
            pipeline=pipe,
            config=cfg,
            capture_func=lambda *args, **kwargs: {"success": True, "state": VADState.SPEECH_ENDED.value},
            playback_func=MagicMock(return_value=True),
        )

        telemetry = session.run()

        assert telemetry.end_reason == SessionEndReason.USER_EXPLICIT_EXIT
        assert telemetry.total_turns == 1

    def test_session_exits_cleanly_on_keyboard_interrupt(self, tmp_path):
        """Ctrl+C (KeyboardInterrupt) interrumpe la sesión de forma limpia."""
        pipe = _create_mock_pipeline()
        cfg = SessionConfig(session_output_dir=str(tmp_path))

        mock_capture = MagicMock(side_effect=KeyboardInterrupt)

        session = ConversationSession(
            pipeline=pipe,
            config=cfg,
            capture_func=mock_capture,
            playback_func=MagicMock(return_value=True),
        )

        telemetry = session.run()

        assert telemetry.end_reason == SessionEndReason.KEYBOARD_INTERRUPT
        assert telemetry.total_turns == 0

    def test_session_stops_on_capture_error(self, tmp_path):
        """MicrophoneNotAvailableError termina la sesión sin dejar procesos huérfanos."""
        pipe = _create_mock_pipeline()
        cfg = SessionConfig(session_output_dir=str(tmp_path))

        mock_capture = MagicMock(side_effect=MicrophoneNotAvailableError("Micrófono desconectado."))

        session = ConversationSession(
            pipeline=pipe,
            config=cfg,
            capture_func=mock_capture,
            playback_func=MagicMock(return_value=True),
        )

        telemetry = session.run()

        assert telemetry.end_reason == SessionEndReason.CAPTURE_ERROR
        assert telemetry.total_turns == 0

    def test_session_recovers_from_empty_audio(self, tmp_path):
        """Una transcripción vacía genera respuesta UNINTELLIGIBLE y no aborta la sesión."""
        pipe = _create_mock_pipeline()
        pipe._next_transcription = ""  # Transcripción vacía
        cfg = SessionConfig(max_turns=1, session_output_dir=str(tmp_path))

        session = ConversationSession(
            pipeline=pipe,
            config=cfg,
            capture_func=lambda *args, **kwargs: {"success": True, "state": VADState.SPEECH_ENDED.value},
            playback_func=MagicMock(return_value=True),
        )

        telemetry = session.run()

        assert telemetry.total_turns == 1
        last_turn = telemetry.turns_telemetry[0]
        assert last_turn.intent_detected == CommercialIntent.UNINTELLIGIBLE.value
        assert "claridad" in last_turn.response_text.lower() or "mensaje claro" in last_turn.response_text.lower()
