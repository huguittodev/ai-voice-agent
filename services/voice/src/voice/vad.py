"""Módulo de detección de actividad de voz (VAD) y fin de turno conversacional (Incremento 3.1).

Proporciona detección de inicio de habla, preservación de pausas internas y detección
de fin de intervención delimitada por silencios configurables, sin dependencias pesadas.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

import numpy as np


class VADState(str, Enum):
    """Estados del autómata de detección de habla y fin de turno."""
    WAITING_FOR_SPEECH = "waiting_for_speech"
    IN_SPEECH = "in_speech"
    SPEECH_ENDED = "speech_ended"
    TIMEOUT_NO_SPEECH = "timeout_no_speech"
    MAX_DURATION_REACHED = "max_duration_reached"


@dataclass
class VADConfig:
    """Configuración del detector de voz y delimitador de turnos.
    
    Attributes:
        sample_rate: Frecuencia de muestreo en Hz (por defecto 16000 Hz PCM).
        chunk_size_samples: Tamaño de bloque en muestras (480 muestras = 30 ms a 16 kHz).
        energy_threshold: Umbral RMS para considerar presencia de voz (float normalizado).
        min_speech_duration_ms: Milisegundos sostenidos para confirmar arranque de voz (evita ruidos y clics).
        silence_hangover_ms: Milisegundos de silencio para decretar fin de turno (configurable, default 800 ms).
        max_utterance_duration_s: Límite de seguridad de duración máxima de intervención (default 15.0 s).
        initial_silence_timeout_s: Tiempo máximo de espera antes de declarar ausencia de voz (default 8.0 s).
        pre_speech_padding_ms: Audio previo al inicio de voz conservado en búfer para no recortar consonantes (default 150 ms).
    """
    sample_rate: int = 16000
    chunk_size_samples: int = 480
    energy_threshold: float = 0.015
    min_speech_duration_ms: float = 120.0
    silence_hangover_ms: float = 800.0
    max_utterance_duration_s: float = 15.0
    initial_silence_timeout_s: float = 8.0
    pre_speech_padding_ms: float = 150.0


@dataclass
class VADDecision:
    """Resultado del procesamiento de un bloque de audio."""
    state: VADState
    is_speech_chunk: bool
    rms_energy: float
    speech_duration_ms: float
    silence_duration_ms: float
    total_elapsed_ms: float


@dataclass
class VADSegmentResult:
    """Resultado final consolidado tras la detección de una intervención."""
    state: VADState
    audio_pcm: np.ndarray
    duration_seconds: float
    speech_start_ms: float | None
    speech_end_ms: float | None
    total_speech_duration_ms: float
    peak_rms: float
    chunks_processed: int


class BaseVoiceActivityDetector(Protocol):
    """Interfaz estándar para detectores de actividad de voz intercambiables."""

    def process_chunk(self, chunk: np.ndarray) -> VADDecision:
        ...

    def reset(self) -> None:
        ...


class EnergyVoiceActivityDetector:
    """Detector de actividad de voz basado en energía RMS y máquina de estados temporal.
    
    Implementa un detector eficiente en CPU sobre NumPy puro (cero dependencias externas nuevas),
    con tolerancia estricta a pausas breves de reflexión (300-500 ms) y corte controlado tras
    el umbral configurable de silencio (silence_hangover_ms).
    """

    def __init__(self, config: VADConfig | None = None) -> None:
        self.config = config if config is not None else VADConfig()
        self.state = VADState.WAITING_FOR_SPEECH

        # Muestras por bloque y conversor de tiempo
        self._chunk_duration_ms = (self.config.chunk_size_samples / self.config.sample_rate) * 1000.0
        self._max_pre_speech_chunks = max(1, int(self.config.pre_speech_padding_ms / self._chunk_duration_ms))

        # Acumuladores de estado
        self._consecutive_speech_ms: float = 0.0
        self._consecutive_silence_ms: float = 0.0
        self._total_speech_ms: float = 0.0
        self._total_elapsed_ms: float = 0.0
        self._peak_rms: float = 0.0
        self._chunks_count: int = 0

        # Marcas de tiempo de voz
        self._speech_start_ms: float | None = None
        self._speech_end_ms: float | None = None

        # Búferes de audio
        self._pre_speech_ring_buffer: list[np.ndarray] = []
        self._captured_chunks: list[np.ndarray] = []

    def reset(self) -> None:
        """Reinicia el detector para una nueva intervención."""
        self.state = VADState.WAITING_FOR_SPEECH
        self._consecutive_speech_ms = 0.0
        self._consecutive_silence_ms = 0.0
        self._total_speech_ms = 0.0
        self._total_elapsed_ms = 0.0
        self._peak_rms = 0.0
        self._chunks_count = 0
        self._speech_start_ms = None
        self._speech_end_ms = None
        self._pre_speech_ring_buffer.clear()
        self._captured_chunks.clear()

    @staticmethod
    def calculate_rms(chunk: np.ndarray) -> float:
        """Calcula el valor cuadrático medio (RMS) de un bloque de audio normalizado."""
        if len(chunk) == 0:
            return 0.0
        # Soporta int16 o float32
        if np.issubdtype(chunk.dtype, np.integer):
            float_chunk = chunk.astype(np.float32) / 32768.0
        else:
            float_chunk = chunk.astype(np.float32)

        mean_square = float(np.mean(float_chunk ** 2))
        return float(np.sqrt(max(0.0, mean_square)))

    def process_chunk(self, chunk: np.ndarray) -> VADDecision:
        """Procesa un bloque de audio y actualiza la máquina de estados de turno."""
        # Si ya se alcanzó un estado terminal, no alterar el resultado
        if self.state in (VADState.SPEECH_ENDED, VADState.TIMEOUT_NO_SPEECH, VADState.MAX_DURATION_REACHED):
            return VADDecision(
                state=self.state,
                is_speech_chunk=False,
                rms_energy=0.0,
                speech_duration_ms=self._total_speech_ms,
                silence_duration_ms=self._consecutive_silence_ms,
                total_elapsed_ms=self._total_elapsed_ms,
            )

        self._chunks_count += 1
        rms = self.calculate_rms(chunk)
        self._peak_rms = max(self._peak_rms, rms)

        self._total_elapsed_ms += self._chunk_duration_ms
        is_speech = rms >= self.config.energy_threshold

        # --- ESTADO 1: ESPERANDO ARRANQUE DE VOZ ---
        if self.state == VADState.WAITING_FOR_SPEECH:
            # Mantener buffer circular para no recortar la consonante inicial
            self._pre_speech_ring_buffer.append(chunk.copy())
            if len(self._pre_speech_ring_buffer) > self._max_pre_speech_chunks:
                self._pre_speech_ring_buffer.pop(0)

            if is_speech:
                self._consecutive_speech_ms += self._chunk_duration_ms
                if self._consecutive_speech_ms >= self.config.min_speech_duration_ms:
                    # Voz confirmada: transferir pre-búfer al audio capturado
                    self.state = VADState.IN_SPEECH
                    self._speech_start_ms = max(0.0, self._total_elapsed_ms - self._consecutive_speech_ms)
                    self._captured_chunks.extend(self._pre_speech_ring_buffer)
                    self._pre_speech_ring_buffer.clear()
                    self._total_speech_ms += self._consecutive_speech_ms
                    self._consecutive_silence_ms = 0.0
            else:
                self._consecutive_speech_ms = 0.0
                # Comprobar límite de tiempo sin que el usuario empiece a hablar
                if (self._total_elapsed_ms / 1000.0) >= self.config.initial_silence_timeout_s:
                    self.state = VADState.TIMEOUT_NO_SPEECH

        # --- ESTADO 2: VOZ ACTIVA EN CURSO ---
        elif self.state == VADState.IN_SPEECH:
            self._captured_chunks.append(chunk.copy())

            if is_speech:
                self._total_speech_ms += self._chunk_duration_ms
                self._consecutive_silence_ms = 0.0
            else:
                self._consecutive_silence_ms += self._chunk_duration_ms

                # Decisión de fin de turno tras silencio sostenido >= silence_hangover_ms
                if self._consecutive_silence_ms >= self.config.silence_hangover_ms:
                    self.state = VADState.SPEECH_ENDED
                    self._speech_end_ms = self._total_elapsed_ms - self._consecutive_silence_ms

            # Límite de seguridad: duración máxima total de la intervención
            if (
                (self._total_elapsed_ms / 1000.0) >= self.config.max_utterance_duration_s
                and self.state != VADState.SPEECH_ENDED
            ):
                self.state = VADState.MAX_DURATION_REACHED
                self._speech_end_ms = self._total_elapsed_ms

        return VADDecision(
            state=self.state,
            is_speech_chunk=is_speech,
            rms_energy=rms,
            speech_duration_ms=self._total_speech_ms,
            silence_duration_ms=self._consecutive_silence_ms,
            total_elapsed_ms=self._total_elapsed_ms,
        )

    def get_consolidated_result(self) -> VADSegmentResult:
        """Devuelve el audio acumulado y los metadatos de la intervención capturada."""
        if self._captured_chunks:
            audio_data = np.concatenate(self._captured_chunks, axis=0)
        else:
            audio_data = np.array([], dtype=np.int16)

        duration_s = len(audio_data) / float(self.config.sample_rate) if len(audio_data) > 0 else 0.0

        return VADSegmentResult(
            state=self.state,
            audio_pcm=audio_data,
            duration_seconds=round(duration_s, 3),
            speech_start_ms=round(self._speech_start_ms, 1) if self._speech_start_ms is not None else None,
            speech_end_ms=round(self._speech_end_ms, 1) if self._speech_end_ms is not None else None,
            total_speech_duration_ms=round(self._total_speech_ms, 1),
            peak_rms=round(self._peak_rms, 4),
            chunks_processed=self._chunks_count,
        )
