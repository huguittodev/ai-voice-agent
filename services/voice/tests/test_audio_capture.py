"""Pruebas automatizadas y unitarias para el módulo de captura de audio y hardware (Fase 1.4).

Utiliza mocks y aislamiento para verificar gestión de timeouts, cancelación de subprocesos,
errores de hardware y regresión de artefactos sin depender de hardware físico real.
"""

import json
import multiprocessing
import os
import time
from unittest.mock import MagicMock, patch
import wave
import pytest

from voice.audio_capture import (
    AudioDeviceStatus,
    AudioPlaybackError,
    MicrophoneNotAvailableError,
    check_audio_hardware,
    play_audio_file,
    record_microphone_speech,
)
from demo_mic import run_mic_dialogue_demo


class TestAudioHardwareInspection:
    """Verifica el comportamiento de detección y validación de dispositivos."""

    def test_check_audio_hardware_structure(self):
        status = check_audio_hardware()
        assert isinstance(status, AudioDeviceStatus)
        assert isinstance(status.has_input_device, bool)
        assert isinstance(status.has_output_device, bool)
        assert isinstance(status.backend_name, str)
        assert isinstance(status.available_devices, list)

    def test_check_audio_hardware_invalid_device_index(self):
        status = check_audio_hardware(device=99999)
        assert not status.has_input_device
        assert "Índice de dispositivo inválido" in (status.error_detail or "")


class TestMicrophoneCaptureRobustness:
    """Pruebas unitarias de captura supervisada, timeouts y liberación de recursos."""

    def test_record_raises_on_invalid_device(self):
        with pytest.raises(MicrophoneNotAvailableError) as exc_info:
            record_microphone_speech("/tmp/test_invalid_dev.wav", duration_seconds=0.1, device=99999)
        assert "no se puede capturar" in str(exc_info.value).lower() or "inválido" in str(exc_info.value).lower()

    def test_record_raises_when_no_input_device(self):
        with patch("voice.audio_capture.check_audio_hardware") as mock_check:
            mock_check.return_value = AudioDeviceStatus(
                has_input_device=False,
                has_output_device=False,
                backend_name="test_backend",
                input_device_name=None,
                output_device_name=None,
                error_detail="Simulación sin dispositivo",
            )
            with pytest.raises(MicrophoneNotAvailableError) as exc_info:
                record_microphone_speech("/tmp/test_no_dev.wav", duration_seconds=0.1)
            assert "simulación sin dispositivo" in str(exc_info.value).lower()

    def test_record_handles_worker_starvation_error(self):
        """Simula que el worker de captura reporta inanición de muestras (0 samples)."""
        def fake_worker(out_path, dur, sr, ch, dev, queue):
            queue.put({
                "success": False,
                "error": "Inanición de muestras: 0 datos recibidos del dispositivo.",
            })

        with patch("multiprocessing.context.SpawnProcess") as mock_proc_cls:
            mock_proc = MagicMock()
            mock_proc.is_alive.return_value = False
            mock_proc.exitcode = 0
            mock_proc_cls.return_value = mock_proc

            with patch("multiprocessing.context.SpawnContext.Queue") as mock_q_cls:
                mock_queue = MagicMock()
                mock_queue.empty.return_value = False
                mock_queue.get.return_value = {
                    "success": False,
                    "error": "Inanición de muestras: 0 datos recibidos.",
                }
                mock_q_cls.return_value = mock_queue

                with patch("voice.audio_capture.check_audio_hardware") as mock_check:
                    mock_check.return_value = AudioDeviceStatus(
                        has_input_device=True,
                        has_output_device=True,
                        backend_name="test",
                        input_device_name="Fake In",
                        output_device_name="Fake Out",
                        error_detail=None,
                        default_input_index=0,
                    )
                    with pytest.raises(MicrophoneNotAvailableError) as exc_info:
                        record_microphone_speech("/tmp/test_starvation.wav", duration_seconds=0.1, timeout_seconds=0.5)
                    assert "inanición de muestras" in str(exc_info.value).lower()

    def test_record_terminates_child_process_on_timeout(self):
        """Verifica que si el subproceso se bloquea, el supervisor lo cancela forzosamente."""
        with patch("multiprocessing.context.SpawnProcess") as mock_proc_cls:
            mock_proc = MagicMock()
            # El subproceso sigue vivo tras el timeout de join
            mock_proc.is_alive.return_value = True
            mock_proc_cls.return_value = mock_proc

            with patch("voice.audio_capture.check_audio_hardware") as mock_check:
                mock_check.return_value = AudioDeviceStatus(
                    has_input_device=True,
                    has_output_device=True,
                    backend_name="test",
                    input_device_name="Fake In",
                    output_device_name="Fake Out",
                    error_detail=None,
                    default_input_index=0,
                )
                with pytest.raises(MicrophoneNotAvailableError) as exc_info:
                    record_microphone_speech(
                        "/tmp/test_hang.wav",
                        duration_seconds=0.1,
                        timeout_seconds=0.2,
                    )

                # Asegurar que se invocó terminate() y/o kill()
                assert mock_proc.terminate.called
                assert "timeout" in str(exc_info.value).lower()


class TestPlaybackRobustness:
    """Pruebas unitarias de reproducción supervisada."""

    def test_play_missing_file_raises_filenotfound(self):
        with pytest.raises(FileNotFoundError):
            play_audio_file("/tmp/archivo_completamente_inexistente_12345.wav")

    def test_play_terminates_on_hung_output(self):
        """Verifica que un bloqueo en la salida se cancele y retorne False sin congelar el hilo."""
        sample_wav = "output/demo_inputs/scenario_1_service_info_input.wav"
        if not os.path.exists(sample_wav):
            pytest.skip("WAV de prueba no disponible en disco")

        with patch("multiprocessing.context.SpawnProcess") as mock_proc_cls:
            mock_proc = MagicMock()
            mock_proc.is_alive.return_value = True
            mock_proc_cls.return_value = mock_proc

            with patch("voice.audio_capture.check_audio_hardware") as mock_check:
                mock_check.return_value = AudioDeviceStatus(
                    has_input_device=True,
                    has_output_device=True,
                    backend_name="test",
                    input_device_name="Fake In",
                    output_device_name="Fake Out",
                    error_detail=None,
                )
                # Debe retornar False limpiamente
                result = play_audio_file(sample_wav, timeout_seconds=0.2)
                assert result is False
                assert mock_proc.terminate.called


class TestMicDemoIntegration:
    """Pruebas de la lógica de demo_mic (modos de captura y artefactos)."""

    def test_demo_mic_wav_input_mode(self):
        sample_wav = "output/demo_inputs/scenario_1_service_info_input.wav"
        if not os.path.exists(sample_wav):
            pytest.skip("WAV de prueba no disponible en disco")

        out_wav = "/tmp/test_demo_out.wav"
        # Probamos que el modo provisto se registra como wav_input
        with patch("voice.pipeline.ConversationTurnPipeline.load_models"):
            with patch("voice.pipeline.ConversationTurnPipeline.process_turn") as mock_turn:
                from voice.pipeline import TurnTelemetry
                mock_turn.return_value = TurnTelemetry(
                    turn_id=1,
                    input_audio_path=sample_wav,
                    input_audio_duration_s=3.32,
                    stt_inference_ms=10.0,
                    stt_model="small",
                    stt_device="cpu",
                    stt_compute_type="int8",
                    transcribed_text="Hola",
                    decision_ms=1.0,
                    intent_detected="service_info",
                    confidence=1.0,
                    response_text="Hola",
                    tts_synthesis_ms=10.0,
                    tts_model_path="test",
                    output_audio_path=out_wav,
                    output_audio_duration_s=2.0,
                    total_turnaround_ms=21.0,
                    turnaround_rtf=0.1,
                )
                res = run_mic_dialogue_demo(input_file=sample_wav, output_wav=out_wav)
                assert res["capture_mode"] == "wav_input"

    def test_mic_demo_artifacts_valid(self):
        json_path = "output/mic_demo/mic_demo_results.json"
        response_wav = "output/mic_demo/response_speech.wav"

        assert os.path.exists(json_path), f"Falta el informe {json_path}"
        assert os.path.exists(response_wav), f"Falta el audio de respuesta {response_wav}"

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "hardware_status" in data
        assert "metrics" in data
        assert "dialogue" in data
        assert data["metrics"]["total_turnaround_ms"] > 0
        assert data["metrics"]["time_to_audio_available_ms"] > 0

        with wave.open(response_wav, "rb") as wf:
            assert wf.getframerate() == 22050
            assert wf.getnchannels() == 1
            assert wf.getnframes() > 0
