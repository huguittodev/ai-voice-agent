"""Pruebas automatizadas para el pipeline de conversación de turno único y el módulo responder."""

import json
import os
import wave
from unittest.mock import MagicMock

import pytest

from voice.pipeline import ConversationTurnPipeline
from voice.responder import (
    CommercialIntent,
    ConversationContext,
    generate_commercial_response,
)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "pipeline")


class TestCommercialResponder:
    """Pruebas de la lógica determinista de decisión comercial."""

    def test_service_info_intent(self):
        phrases = [
            "¿Qué servicios ofrecéis en vuestra empresa?",
            "Hola, me gustaría saber a qué os dedicáis",
            "¿Cuál es vuestro producto principal?",
            "Información sobre vuestros servicios, por favor",
        ]
        for phrase in phrases:
            resp = generate_commercial_response(phrase)
            assert resp.intent == CommercialIntent.SERVICE_INFO
            assert "asistente virtual" in resp.response_text.lower()
            assert "¿qué tipo de proceso" in resp.response_text.lower()
            # Seguridad: no inventa precios
            assert (
                "€" not in resp.response_text
                and "euro" not in resp.response_text.lower()
            )

    def test_express_interest_intent(self):
        phrases = [
            "Me interesa bastante la propuesta",
            "¿Podéis enviar más información por correo?",
            "Estoy interesado en recibir un catálogo con detalles",
        ]
        for phrase in phrases:
            resp = generate_commercial_response(phrase)
            assert resp.intent == CommercialIntent.EXPRESS_INTEREST
            assert "correo electrónico" in resp.response_text.lower()
            # Seguridad: no promete fechas falsas de entrega
            assert "inmediato" not in resp.response_text.lower()

    def test_meeting_request_intent(self):
        phrases = [
            "Me gustaría agendar una reunión para el próximo jueves",
            "¿Podemos concertar una videollamada para vernos?",
            "Quiero tener una llamada con vosotros",
        ]
        for phrase in phrases:
            resp = generate_commercial_response(phrase)
            assert resp.intent == CommercialIntent.MEETING_REQUEST
            # Seguridad: una petición de reunión no es una reserva confirmada
            assert "revisará la agenda y le confirmará" in resp.response_text.lower()
            assert "confirmada" not in resp.response_text.lower()

    def test_unintelligible_or_empty_intent(self):
        cases = [
            "",
            "   ",
            "[música]",
            "[ruido]",
            "...",
            "a",
            "eh",
        ]
        for case in cases:
            resp = generate_commercial_response(case)
            assert resp.intent == CommercialIntent.UNINTELLIGIBLE
            assert (
                "no he podido escucharle con claridad" in resp.response_text.lower()
                or "mensaje claro" in resp.response_text.lower()
            )

    def test_fallback_intent(self):
        phrase = "Hoy hace un día bastante soleado en Madrid"
        resp = generate_commercial_response(phrase)
        assert resp.intent == CommercialIntent.FALLBACK_CLARIFICATION
        assert "¿le gustaría conocer nuestros servicios" in resp.response_text.lower()


class TestPipelineArtifacts:
    """Pruebas de verificación de los artefactos generados en la demostración."""

    def test_reply_audio_files_exist_and_valid(self):
        scenarios = [
            "scenario_1_service_info",
            "scenario_2_interest",
            "scenario_3_meeting",
            "scenario_4_unintelligible",
        ]
        for sc in scenarios:
            wav_path = os.path.join(OUTPUT_DIR, f"{sc}_reply.wav")
            if not os.path.exists(wav_path):
                pytest.skip(f"Falta archivo de demostración: {wav_path}")
            assert os.path.getsize(wav_path) > 10000, (
                f"Archivo demasiado pequeño: {wav_path}"
            )
            with wave.open(wav_path, "rb") as wf:
                assert wf.getframerate() == 22050
                assert wf.getnchannels() == 1
                assert wf.getnframes() > 0

    def test_pipeline_results_telemetry(self):
        json_path = os.path.join(OUTPUT_DIR, "turn_pipeline_results.json")
        if not os.path.exists(json_path):
            pytest.skip(f"Falta archivo de telemetría de demo: {json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "cold_load" in data
        assert "averages_turnaround" in data
        assert len(data["scenarios"]) == 4

        # Comprobar que la latencia media de turno está por debajo del umbral razonable (< 2000 ms)
        avg_total = data["averages_turnaround"]["avg_total_turnaround_ms"]
        assert avg_total < 2000.0, f"Latencia media excesiva: {avg_total} ms"

        # Comprobar que la decisión determinista toma menos de 5 ms
        avg_dec = data["averages_turnaround"]["avg_decision_ms"]
        assert avg_dec < 5.0, f"Decisión de reglas demasiado lenta: {avg_dec} ms"


class TestPipelineContextRetention:
    """Pruebas de retención de estado conversacional entre turnos en ConversationTurnPipeline."""

    def _create_mocked_pipeline(self) -> ConversationTurnPipeline:
        pipeline = ConversationTurnPipeline()
        pipeline.whisper_model = MagicMock()
        pipeline.piper_voice = MagicMock()

        def _mock_synthesize_wav(text: str, wav_file: wave.Wave_write) -> None:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            wav_file.writeframes(b"\x00" * 4410)

        pipeline.piper_voice.synthesize_wav = MagicMock(side_effect=_mock_synthesize_wav)
        pipeline.is_loaded = True
        return pipeline

    def test_pipeline_retains_context_across_turns(self, tmp_path):
        """Demuestra que process_turn acumula turnos y respeta el rechazo sin insistir."""
        pipeline = self._create_mocked_pipeline()
        in_wav = str(tmp_path / "dummy_in.wav")
        out_wav = str(tmp_path / "dummy_out.wav")

        with wave.open(in_wav, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00" * 3200)

        # Turno 1: Rechazo comercial
        seg1 = MagicMock()
        seg1.text = "No me interesa vuestra propuesta comercial"
        pipeline.whisper_model.transcribe.return_value = ([seg1], None)

        telemetry_turn1 = pipeline.process_turn(in_wav, out_wav)
        assert telemetry_turn1.intent_detected == CommercialIntent.SOFT_REJECTION.value
        assert pipeline.active_context.is_rejected is True
        assert pipeline.active_context.turn_count == 1

        # Turno 2: Saludo neutro subsiguiente ("Hola, buenos días")
        seg2 = MagicMock()
        seg2.text = "Hola, buenos días"
        pipeline.whisper_model.transcribe.return_value = ([seg2], None)

        telemetry_turn2 = pipeline.process_turn(in_wav, out_wav)
        # Seguridad: no debe reiniciar el pitch de venta (GREETING_PRESENTATION)
        assert telemetry_turn2.intent_detected == CommercialIntent.SOFT_REJECTION.value
        assert "no continuar" in telemetry_turn2.response_text.lower()
        assert pipeline.active_context.turn_count == 2

    def test_pipeline_dnc_locks_session(self, tmp_path):
        """Demuestra que tras una petición DNC, el estado no se reactiva comercialmente."""
        pipeline = self._create_mocked_pipeline()
        in_wav = str(tmp_path / "dummy_in.wav")
        out_wav = str(tmp_path / "dummy_out.wav")

        with wave.open(in_wav, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00" * 3200)

        # Turno 1: DNC
        seg1 = MagicMock()
        seg1.text = "No volváis a molestarme nunca más"
        pipeline.whisper_model.transcribe.return_value = ([seg1], None)

        telemetry1 = pipeline.process_turn(in_wav, out_wav)
        assert telemetry1.intent_detected == CommercialIntent.DO_NOT_CONTACT.value
        assert pipeline.active_context.is_do_not_contact is True
        assert "no volver a contactarle" in telemetry1.response_text.lower()
        assert "no continuaremos" in telemetry1.response_text.lower()

        # Turno 2: Mensaje posterior intentando pedir precio
        seg2 = MagicMock()
        seg2.text = "¿Cuánto cuesta?"
        pipeline.whisper_model.transcribe.return_value = ([seg2], None)

        telemetry2 = pipeline.process_turn(in_wav, out_wav)
        assert telemetry2.intent_detected == CommercialIntent.DO_NOT_CONTACT.value
        assert pipeline.active_context.is_do_not_contact is True
        assert "no volveremos a contactarle" in telemetry2.response_text.lower()
        assert "concluida" in telemetry2.response_text.lower()
        # Seguridad: no reactiva la venta ni inventa precios
        assert "tarifa" not in telemetry2.response_text.lower()
        assert "precio" not in telemetry2.response_text.lower()
        assert "€" not in telemetry2.response_text and "euro" not in telemetry2.response_text.lower()

    def test_pipeline_reset_conversation_clears_state(self):
        """Demuestra que reset_conversation devuelve un contexto limpio."""
        pipeline = self._create_mocked_pipeline()
        pipeline.active_context.is_rejected = True
        pipeline.active_context.is_do_not_contact = True
        pipeline.active_context.turn_count = 5

        new_ctx = pipeline.reset_conversation()
        assert new_ctx.turn_count == 0
        assert new_ctx.is_rejected is False
        assert new_ctx.is_do_not_contact is False
        assert pipeline.active_context is new_ctx

    def test_pipeline_isolated_explicit_context(self, tmp_path):
        """Demuestra que pasar un contexto explícito no contamina active_context."""
        pipeline = self._create_mocked_pipeline()
        explicit_ctx = ConversationContext()
        in_wav = str(tmp_path / "dummy_in.wav")
        out_wav = str(tmp_path / "dummy_out.wav")

        with wave.open(in_wav, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00" * 3200)

        seg = MagicMock()
        seg.text = "Borrad mis datos"
        pipeline.whisper_model.transcribe.return_value = ([seg], None)

        pipeline.process_turn(in_wav, out_wav, context=explicit_ctx)
        assert explicit_ctx.is_do_not_contact is True
        assert explicit_ctx.turn_count == 1

        # active_context del pipeline debe permanecer intacto
        assert pipeline.active_context.is_do_not_contact is False
        assert pipeline.active_context.turn_count == 0
