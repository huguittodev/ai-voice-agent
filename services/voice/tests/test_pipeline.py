"""Pruebas automatizadas para el pipeline de conversación de turno único y el módulo responder."""

import json
import os
import wave

from voice.responder import (
    CommercialIntent,
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
            assert os.path.exists(wav_path), f"Falta el archivo generado {wav_path}"
            assert os.path.getsize(wav_path) > 10000, (
                f"Archivo demasiado pequeño: {wav_path}"
            )
            with wave.open(wav_path, "rb") as wf:
                assert wf.getframerate() == 22050
                assert wf.getnchannels() == 1
                assert wf.getnframes() > 0

    def test_pipeline_results_telemetry(self):
        json_path = os.path.join(OUTPUT_DIR, "turn_pipeline_results.json")
        assert os.path.exists(json_path), f"Falta el informe {json_path}"
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
