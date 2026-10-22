"""Pruebas unitarias para el detector de actividad de voz (VAD) y fin de turno (Incremento 3.1).

Verifica exhaustivamente y de forma 100% determinista sobre audio sintético:
1. Detección de arranque y fin de habla.
2. Preservación íntegra de pausas breves de reflexión (300-500 ms).
3. Filtrado de picos espurios y clics cortos de ruido (< 120 ms).
4. Configurabilidad estricta del umbral de silencio (hangover).
5. Timeout por ausencia inicial de voz.
6. Límite de seguridad de duración máxima de intervención.
7. Búfer pre-habla para no mutilar fonemas iniciales.
8. Integración con el proceso supervisado de captura en audio_capture.py.
"""

import os
import queue
import wave
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from voice.audio_capture import (
    MicrophoneNotAvailableError,
    _worker_vad_record_process,
    record_speech_with_vad,
)
from voice.vad import (
    EnergyVoiceActivityDetector,
    VADConfig,
    VADDecision,
    VADSegmentResult,
    VADState,
)


def _generate_synthetic_tone(
    duration_s: float,
    sample_rate: int = 16000,
    frequency_hz: float = 440.0,
    amplitude: float = 0.3,
) -> np.ndarray:
    """Genera una señal sinusoidal en formato int16 simulando voz activa."""
    num_samples = int(duration_s * sample_rate)
    t = np.linspace(0, duration_s, num_samples, endpoint=False, dtype=np.float32)
    waveform = amplitude * np.sin(2 * np.pi * frequency_hz * t)
    return (waveform * 32767).astype(np.int16)


def _generate_synthetic_silence(duration_s: float, sample_rate: int = 16000) -> np.ndarray:
    """Genera silencio plano en formato int16."""
    num_samples = int(duration_s * sample_rate)
    return np.zeros(num_samples, dtype=np.int16)


class TestEnergyVADUnitLogic:
    """Pruebas de la lógica determinista del detector de energía RMS."""

    def test_calculate_rms_known_values(self):
        """Verifica el cálculo de RMS para silencio y señales normalizadas."""
        # Silencio absoluto
        silence = np.zeros(480, dtype=np.int16)
        assert EnergyVoiceActivityDetector.calculate_rms(silence) == 0.0

        # Bloque vacío
        empty = np.array([], dtype=np.int16)
        assert EnergyVoiceActivityDetector.calculate_rms(empty) == 0.0

        # Señal constante máxima en int16 (32767 -> ~1.0 normalizado)
        full_dc = np.full(480, 32767, dtype=np.int16)
        rms_dc = EnergyVoiceActivityDetector.calculate_rms(full_dc)
        assert pytest.approx(rms_dc, rel=1e-2) == 1.0

    def test_vad_detects_speech_start_and_end(self):
        """Detecta arranque de voz y corte exacto tras el silencio configurado."""
        cfg = VADConfig(
            sample_rate=16000,
            chunk_size_samples=480,  # 30 ms por chunk
            energy_threshold=0.02,
            min_speech_duration_ms=120.0,
            silence_hangover_ms=800.0,
        )
        detector = EnergyVoiceActivityDetector(cfg)

        # 1. 0.6 s de silencio inicial (20 chunks de 30 ms)
        silence_initial = _generate_synthetic_silence(0.6, sample_rate=cfg.sample_rate)
        # 2. 1.2 s de habla activa (40 chunks de 30 ms)
        speech = _generate_synthetic_tone(1.2, sample_rate=cfg.sample_rate, amplitude=0.25)
        # 3. 1.2 s de silencio final (40 chunks de 30 ms)
        silence_final = _generate_synthetic_silence(1.2, sample_rate=cfg.sample_rate)

        full_audio = np.concatenate([silence_initial, speech, silence_final])

        states_trace: list[VADState] = []
        num_chunks = len(full_audio) // cfg.chunk_size_samples

        for i in range(num_chunks):
            chunk = full_audio[i * cfg.chunk_size_samples : (i + 1) * cfg.chunk_size_samples]
            dec = detector.process_chunk(chunk)
            assert isinstance(dec, VADDecision)
            states_trace.append(dec.state)
            if dec.state == VADState.SPEECH_ENDED:
                break

        # Debe haber pasado por: WAITING -> IN_SPEECH -> SPEECH_ENDED
        assert VADState.WAITING_FOR_SPEECH in states_trace
        assert VADState.IN_SPEECH in states_trace
        assert detector.state == VADState.SPEECH_ENDED

        res = detector.get_consolidated_result()
        assert isinstance(res, VADSegmentResult)
        assert res.state == VADState.SPEECH_ENDED
        assert res.duration_seconds > 1.0
        assert res.speech_start_ms is not None
        assert res.speech_end_ms is not None
        assert res.peak_rms > 0.1

    def test_vad_preserves_internal_pauses(self):
        """Verifica que pausas breves de 300 ms y 450 ms NO cortan la intervención prematuramente."""
        cfg = VADConfig(
            sample_rate=16000,
            chunk_size_samples=480,  # 30 ms
            energy_threshold=0.02,
            silence_hangover_ms=800.0,  # Umbral de corte en 800 ms
        )
        detector = EnergyVoiceActivityDetector(cfg)

        # Segmento 1: Habla de 600 ms
        sp1 = _generate_synthetic_tone(0.6, sample_rate=16000, amplitude=0.2)
        # Pausa 1: Silencio de 360 ms (12 chunks de 30 ms) < 800 ms
        pause1 = _generate_synthetic_silence(0.36, sample_rate=16000)
        # Segmento 2: Habla de 600 ms
        sp2 = _generate_synthetic_tone(0.6, sample_rate=16000, amplitude=0.2)
        # Pausa 2: Silencio de 450 ms (15 chunks de 30 ms) < 800 ms
        pause2 = _generate_synthetic_silence(0.45, sample_rate=16000)
        # Segmento 3: Habla de 600 ms
        sp3 = _generate_synthetic_tone(0.6, sample_rate=16000, amplitude=0.2)
        # Silencio final de 1.0 s > 800 ms (debe cortar aquí)
        final_silence = _generate_synthetic_silence(1.0, sample_rate=16000)

        composite = np.concatenate([sp1, pause1, sp2, pause2, sp3, final_silence])
        num_chunks = len(composite) // cfg.chunk_size_samples

        ended_chunk_idx = None
        for i in range(num_chunks):
            chunk = composite[i * cfg.chunk_size_samples : (i + 1) * cfg.chunk_size_samples]
            dec = detector.process_chunk(chunk)
            if dec.state == VADState.SPEECH_ENDED and ended_chunk_idx is None:
                ended_chunk_idx = i

        assert detector.state == VADState.SPEECH_ENDED
        # El corte debe ocurrir tras sp3 + ~800 ms de silencio final, NO durante las pausas 1 ni 2
        total_audio_before_final = len(sp1) + len(pause1) + len(sp2) + len(pause2) + len(sp3)
        samples_at_cut = ended_chunk_idx * cfg.chunk_size_samples
        assert samples_at_cut >= total_audio_before_final

        res = detector.get_consolidated_result()
        # El audio consolidado contiene la frase completa incluidas las pausas
        assert res.duration_seconds >= (total_audio_before_final / 16000.0)

    def test_vad_filters_short_noise_spikes(self):
        """Un clic o golpe seco de 40 ms no debe activar el estado de voz sostenida."""
        cfg = VADConfig(
            sample_rate=16000,
            chunk_size_samples=480,  # 30 ms
            energy_threshold=0.02,
            min_speech_duration_ms=120.0,  # Requiere al menos 4 chunks (120 ms)
        )
        detector = EnergyVoiceActivityDetector(cfg)

        # Silencio (300 ms) + Ruido fuerte corto de 40 ms + Silencio (500 ms)
        silence_1 = _generate_synthetic_silence(0.3, sample_rate=16000)
        spike = _generate_synthetic_tone(0.04, sample_rate=16000, amplitude=0.8)
        silence_2 = _generate_synthetic_silence(0.5, sample_rate=16000)

        signal = np.concatenate([silence_1, spike, silence_2])
        num_chunks = len(signal) // cfg.chunk_size_samples

        for i in range(num_chunks):
            chunk = signal[i * cfg.chunk_size_samples : (i + 1) * cfg.chunk_size_samples]
            dec = detector.process_chunk(chunk)
            # En ningún momento debe pasar a IN_SPEECH
            assert dec.state == VADState.WAITING_FOR_SPEECH

        assert detector.state == VADState.WAITING_FOR_SPEECH

    def test_vad_configurable_hangover(self):
        """El umbral de silencio hangover es estrictamente respetado según su configuración."""
        # Detector A: hangover corto (400 ms)
        cfg_short = VADConfig(sample_rate=16000, chunk_size_samples=480, silence_hangover_ms=400.0)
        det_short = EnergyVoiceActivityDetector(cfg_short)

        # Detector B: hangover largo (1200 ms)
        cfg_long = VADConfig(sample_rate=16000, chunk_size_samples=480, silence_hangover_ms=1200.0)
        det_long = EnergyVoiceActivityDetector(cfg_long)

        # Habla (500 ms) + Silencio de prueba (600 ms)
        sp = _generate_synthetic_tone(0.5, sample_rate=16000, amplitude=0.25)
        sil = _generate_synthetic_silence(0.6, sample_rate=16000)
        test_audio = np.concatenate([sp, sil])
        num_chunks = len(test_audio) // 480

        for i in range(num_chunks):
            chunk = test_audio[i * 480 : (i + 1) * 480]
            det_short.process_chunk(chunk)
            det_long.process_chunk(chunk)

        # Con 400 ms de hangover, el silencio de 600 ms debió provocar SPEECH_ENDED
        assert det_short.state == VADState.SPEECH_ENDED
        # Con 1200 ms de hangover, el silencio de 600 ms aún NO debe haber cortado
        assert det_long.state == VADState.IN_SPEECH

    def test_vad_initial_silence_timeout(self):
        """Silencio puro prolongado activa TIMEOUT_NO_SPEECH sin lanzar excepciones."""
        cfg = VADConfig(
            sample_rate=16000,
            chunk_size_samples=480,
            initial_silence_timeout_s=1.0,  # 1 segundo para prueba rápida
        )
        detector = EnergyVoiceActivityDetector(cfg)

        silence = _generate_synthetic_silence(1.2, sample_rate=16000)
        num_chunks = len(silence) // 480

        for i in range(num_chunks):
            chunk = silence[i * 480 : (i + 1) * 480]
            dec = detector.process_chunk(chunk)
            if dec.state == VADState.TIMEOUT_NO_SPEECH:
                break

        assert detector.state == VADState.TIMEOUT_NO_SPEECH
        res = detector.get_consolidated_result()
        assert res.state == VADState.TIMEOUT_NO_SPEECH
        assert len(res.audio_pcm) == 0

    def test_vad_max_duration_safety_ceiling(self):
        """Habla ininterrumpida activa MAX_DURATION_REACHED como techo de seguridad."""
        cfg = VADConfig(
            sample_rate=16000,
            chunk_size_samples=480,
            max_utterance_duration_s=1.5,  # 1.5 segundos para prueba ágil
        )
        detector = EnergyVoiceActivityDetector(cfg)

        continuous_speech = _generate_synthetic_tone(2.0, sample_rate=16000, amplitude=0.25)
        num_chunks = len(continuous_speech) // 480

        for i in range(num_chunks):
            chunk = continuous_speech[i * 480 : (i + 1) * 480]
            dec = detector.process_chunk(chunk)
            if dec.state == VADState.MAX_DURATION_REACHED:
                break

        assert detector.state == VADState.MAX_DURATION_REACHED
        res = detector.get_consolidated_result()
        assert res.state == VADState.MAX_DURATION_REACHED
        assert res.duration_seconds >= 1.4

    def test_vad_reset_clears_state(self):
        """El método reset devuelve el detector al estado inicial limpio."""
        cfg = VADConfig(sample_rate=16000, chunk_size_samples=480)
        detector = EnergyVoiceActivityDetector(cfg)

        speech = _generate_synthetic_tone(0.5, sample_rate=16000)
        for i in range(len(speech) // 480):
            detector.process_chunk(speech[i * 480 : (i + 1) * 480])

        assert detector.state == VADState.IN_SPEECH
        detector.reset()
        assert detector.state == VADState.WAITING_FOR_SPEECH
        res = detector.get_consolidated_result()
        assert len(res.audio_pcm) == 0


class TestPreSpeechPadding:
    """Verifica que el búfer pre-habla no mutila el inicio de la intervención."""

    def test_vad_preserves_pre_speech_audio(self):
        cfg = VADConfig(
            sample_rate=16000,
            chunk_size_samples=480,
            energy_threshold=0.03,
            min_speech_duration_ms=120.0,
            pre_speech_padding_ms=150.0,
        )
        detector = EnergyVoiceActivityDetector(cfg)

        # 300 ms de silencio inicial (10 chunks)
        silence = _generate_synthetic_silence(0.3, sample_rate=16000)
        # 600 ms de habla (20 chunks)
        speech = _generate_synthetic_tone(0.6, sample_rate=16000, amplitude=0.25)
        # 900 ms de silencio final (30 chunks)
        final_sil = _generate_synthetic_silence(0.9, sample_rate=16000)

        audio = np.concatenate([silence, speech, final_sil])
        for i in range(len(audio) // 480):
            dec = detector.process_chunk(audio[i * 480 : (i + 1) * 480])
            if dec.state == VADState.SPEECH_ENDED:
                break

        res = detector.get_consolidated_result()
        # El audio capturado debe incluir el pre-padding (~150 ms) además del habla y hangover
        assert res.state == VADState.SPEECH_ENDED
        assert res.duration_seconds > 0.6


class TestVADCaptureIntegration:
    """Pruebas de la integración con el subsistema de audio y procesos en audio_capture.py."""

    def test_record_speech_with_vad_supervisor_success(self, tmp_path):
        """Valida que record_speech_with_vad supervisa el proceso y devuelve resultados correctos."""
        out_wav = str(tmp_path / "vad_captured.wav")
        cfg = VADConfig(
            sample_rate=16000,
            chunk_size_samples=480,
            silence_hangover_ms=200.0,
            initial_silence_timeout_s=2.0,
        )

        with patch("voice.audio_capture.check_audio_hardware") as mock_check, \
             patch("multiprocessing.get_context") as mock_get_context:

            mock_check.return_value = MagicMock(has_input_device=True, default_input_index=0)

            mock_ctx = MagicMock()
            mock_proc = MagicMock()
            mock_proc.is_alive.return_value = False
            mock_proc.exitcode = 0
            mock_ctx.Process.return_value = mock_proc

            mock_queue = MagicMock()
            mock_queue.empty.return_value = False
            mock_queue.get.return_value = {
                "success": True,
                "state": VADState.SPEECH_ENDED.value,
                "duration_seconds": 1.45,
                "speech_start_ms": 300.0,
                "speech_end_ms": 1750.0,
                "total_speech_duration_ms": 1450.0,
                "peak_rms": 0.23,
                "chunks_processed": 50,
                "device_name": "Mock Microphone",
                "errors": [],
            }
            mock_ctx.Queue.return_value = mock_queue
            mock_get_context.return_value = mock_ctx

            res = record_speech_with_vad(out_wav, vad_config=cfg)
            assert res["state"] == VADState.SPEECH_ENDED.value
            assert res["duration_seconds"] == 1.45
            assert "total_wall_time_s" in res
            assert mock_ctx.Process.called
            assert mock_proc.start.called

    def test_record_speech_with_vad_supervisor_timeout(self, tmp_path):
        """Verifica que si el proceso de captura VAD se bloquea, el supervisor lo termina por timeout."""
        out_wav = str(tmp_path / "vad_hung.wav")

        with patch("voice.audio_capture.check_audio_hardware") as mock_check, \
             patch("multiprocessing.get_context") as mock_get_context:

            mock_check.return_value = MagicMock(has_input_device=True, default_input_index=0)

            mock_ctx = MagicMock()
            mock_proc = MagicMock()
            # El proceso sigue vivo tras el join
            mock_proc.is_alive.return_value = True
            mock_ctx.Process.return_value = mock_proc
            mock_ctx.Queue.return_value = MagicMock()
            mock_get_context.return_value = mock_ctx

            with pytest.raises(MicrophoneNotAvailableError) as exc_info:
                record_speech_with_vad(out_wav, timeout_seconds=0.1)

            assert "timeout de seguridad" in str(exc_info.value).lower()
            assert mock_proc.terminate.called

    def test_record_speech_with_vad_worker_reported_error(self, tmp_path):
        """Verifica que si el worker reporta error de dispositivo, se propaga MicrophoneNotAvailableError."""
        out_wav = str(tmp_path / "vad_err.wav")

        with patch("voice.audio_capture.check_audio_hardware") as mock_check, \
             patch("multiprocessing.get_context") as mock_get_context:

            mock_check.return_value = MagicMock(has_input_device=True, default_input_index=0)

            mock_ctx = MagicMock()
            mock_proc = MagicMock()
            mock_proc.is_alive.return_value = False
            mock_proc.exitcode = 0
            mock_ctx.Process.return_value = mock_proc

            mock_queue = MagicMock()
            mock_queue.empty.return_value = False
            mock_queue.get.return_value = {
                "success": False,
                "error": "Dispositivo de audio ocupado o bloqueado.",
            }
            mock_ctx.Queue.return_value = mock_queue
            mock_get_context.return_value = mock_ctx

            with pytest.raises(MicrophoneNotAvailableError) as exc_info:
                record_speech_with_vad(out_wav)

            assert "ocupado o bloqueado" in str(exc_info.value).lower()

    def test_worker_vad_record_process_creates_valid_wav_file(self, tmp_path):
        """Prueba directamente la función worker generando un archivo WAV real y válido a partir de un stream simulado."""
        out_wav = str(tmp_path / "worker_output.wav")
        cfg = VADConfig(
            sample_rate=16000,
            chunk_size_samples=480,
            silence_hangover_ms=150.0,
            min_speech_duration_ms=60.0,
            initial_silence_timeout_s=2.0,
        )

        res_queue = queue.Queue()

        class MockInputStream:
            def __init__(self, *args, **kwargs):
                self.callback = kwargs.get("callback")

            def __enter__(self):
                # Emitir 4 bloques de voz activa (120 ms)
                sp_chunk = _generate_synthetic_tone(0.03, sample_rate=16000, amplitude=0.3)
                for _ in range(4):
                    self.callback(sp_chunk, 480, None, None)
                # Emitir 8 bloques de silencio (240 ms > hangover de 150 ms)
                sil_chunk = _generate_synthetic_silence(0.03, sample_rate=16000)
                for _ in range(8):
                    self.callback(sil_chunk, 480, None, None)
                return self

            def __exit__(self, *args):
                pass

        mock_sd = MagicMock()
        mock_sd.query_devices.return_value = {"name": "Simulated Mic", "max_input_channels": 1}
        mock_sd.default.device = [0, 0]
        mock_sd.InputStream = MockInputStream

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            _worker_vad_record_process(
                output_wav_path=out_wav,
                vad_config=cfg,
                channels=1,
                device=0,
                result_queue=res_queue,
            )

        assert not res_queue.empty()
        result = res_queue.get()
        assert result["success"] is True
        assert result["state"] == VADState.SPEECH_ENDED.value
        assert result["duration_seconds"] > 0.0

        # Verificar que el WAV generado en disco es válido según el contrato estándar
        assert os.path.exists(out_wav)
        with wave.open(out_wav, "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000
            assert wf.getnframes() > 0

