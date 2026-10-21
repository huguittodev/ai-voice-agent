"""Pipeline del ciclo de conversación de turno único.

Flujo:
Audio WAV de entrada -> faster-whisper small (CPU int8) -> Texto reconocido ->
Lógica determinista (responder.py) -> Texto de respuesta ->
Piper TTS (davefx en CPU) -> Archivo WAV de respuesta.
"""

import os
import subprocess
import time
import wave
from dataclasses import dataclass

import psutil
from faster_whisper import WhisperModel
from piper.voice import PiperVoice

from voice.responder import CommercialResponse, generate_commercial_response


def _get_vram_mb() -> float:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,nounits,noheader"],
            text=True,
            timeout=2,
        )
        return float(out.strip().split("\n")[0])
    except Exception:
        return 0.0


def _get_audio_duration_seconds(wav_path: str) -> float:
    with wave.open(wav_path, "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return frames / float(rate) if rate > 0 else 0.0


@dataclass
class TurnTelemetry:
    input_wav_path: str
    output_wav_path: str
    input_audio_duration_s: float
    output_audio_duration_s: float

    # Tiempos de procesamiento en milisegundos
    stt_inference_ms: float
    decision_ms: float
    tts_synthesis_ms: float
    total_turnaround_ms: float

    # Factores de tiempo real
    turnaround_rtf: float  # total_turnaround / input_audio_duration

    # Texto
    transcribed_text: str
    response_text: str
    intent_detected: str
    confidence: float

    # Memoria y recursos
    ram_process_mb: float
    vram_mb: float

    # Identificadores de modelo
    stt_model: str
    stt_device: str
    stt_compute_type: str
    tts_model_path: str


class ConversationTurnPipeline:
    """Orquestador persistente del turno conversacional para mediciones warm y cold."""

    def __init__(
        self,
        stt_model_name: str = "small",
        stt_device: str = "cpu",
        stt_compute_type: str = "int8",
        tts_model_path: str = "models/piper/es_ES-davefx-medium/es_ES-davefx-medium.onnx",
        tts_config_path: str = "models/piper/es_ES-davefx-medium/es_ES-davefx-medium.onnx.json",
    ):
        self.stt_model_name = stt_model_name
        self.stt_device = stt_device
        self.stt_compute_type = stt_compute_type
        self.tts_model_path = tts_model_path
        self.tts_config_path = tts_config_path

        self.whisper_model: WhisperModel | None = None
        self.piper_voice: PiperVoice | None = None

        self.cold_load_stt_ms: float = 0.0
        self.cold_load_tts_ms: float = 0.0
        self.is_loaded: bool = False

    def load_models(self) -> None:
        """Carga en memoria los modelos STT y TTS midiendo tiempos de arranque en frío."""
        if self.is_loaded:
            return

        print("[Pipeline] Cargando modelo STT (faster-whisper small)...", flush=True)
        t0 = time.perf_counter()
        self.whisper_model = WhisperModel(
            self.stt_model_name,
            device=self.stt_device,
            compute_type=self.stt_compute_type,
        )
        self.cold_load_stt_ms = (time.perf_counter() - t0) * 1000.0

        print("[Pipeline] Cargando modelo TTS (Piper davefx)...", flush=True)
        t1 = time.perf_counter()
        self.piper_voice = PiperVoice.load(
            self.tts_model_path, config_path=self.tts_config_path
        )
        self.cold_load_tts_ms = (time.perf_counter() - t1) * 1000.0

        self.is_loaded = True
        print(
            f"[Pipeline] Modelos cargados. Cold STT: {self.cold_load_stt_ms:.1f} ms | Cold TTS: {self.cold_load_tts_ms:.1f} ms",
            flush=True,
        )

    def process_turn(self, input_wav_path: str, output_wav_path: str) -> TurnTelemetry:
        """Ejecuta un turno completo de conversación de extremo a extremo."""
        if not self.is_loaded:
            self.load_models()

        assert self.whisper_model is not None
        assert self.piper_voice is not None

        os.makedirs(os.path.dirname(output_wav_path), exist_ok=True)
        input_duration_s = _get_audio_duration_seconds(input_wav_path)

        # Inicio de la medición de latencia de turno (Turnaround Time)
        turn_start = time.perf_counter()

        # 1. Transcripción STT
        t_stt_start = time.perf_counter()
        segments, _ = self.whisper_model.transcribe(
            input_wav_path, language="es", beam_size=5
        )
        transcribed_text = " ".join([seg.text.strip() for seg in segments]).strip()
        stt_inference_ms = (time.perf_counter() - t_stt_start) * 1000.0

        # 2. Generación determinista de respuesta
        t_dec_start = time.perf_counter()
        commercial_resp: CommercialResponse = generate_commercial_response(
            transcribed_text
        )
        response_text = commercial_resp.response_text
        decision_ms = (time.perf_counter() - t_dec_start) * 1000.0

        # 3. Síntesis TTS y escritura directa del archivo WAV de salida
        t_tts_start = time.perf_counter()
        with wave.open(output_wav_path, "wb") as wav_out:
            self.piper_voice.synthesize_wav(response_text, wav_out)
        tts_synthesis_ms = (time.perf_counter() - t_tts_start) * 1000.0

        total_turnaround_s = time.perf_counter() - turn_start
        total_turnaround_ms = total_turnaround_s * 1000.0

        output_duration_s = _get_audio_duration_seconds(output_wav_path)
        turnaround_rtf = (
            total_turnaround_s / input_duration_s if input_duration_s > 0 else 0.0
        )

        process = psutil.Process()
        ram_mb = process.memory_info().rss / (1024 * 1024)
        vram_mb = _get_vram_mb()

        return TurnTelemetry(
            input_wav_path=input_wav_path,
            output_wav_path=output_wav_path,
            input_audio_duration_s=round(input_duration_s, 3),
            output_audio_duration_s=round(output_duration_s, 3),
            stt_inference_ms=round(stt_inference_ms, 2),
            decision_ms=round(decision_ms, 4),
            tts_synthesis_ms=round(tts_synthesis_ms, 2),
            total_turnaround_ms=round(total_turnaround_ms, 2),
            turnaround_rtf=round(turnaround_rtf, 4),
            transcribed_text=transcribed_text,
            response_text=response_text,
            intent_detected=commercial_resp.intent.value,
            confidence=commercial_resp.confidence,
            ram_process_mb=round(ram_mb, 2),
            vram_mb=round(vram_mb, 2),
            stt_model=self.stt_model_name,
            stt_device=self.stt_device,
            stt_compute_type=self.stt_compute_type,
            tts_model_path=self.tts_model_path,
        )
