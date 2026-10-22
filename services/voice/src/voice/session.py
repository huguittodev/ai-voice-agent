"""Orquestador de sesión conversacional continua multi-turno (Incremento 3.2).

Implementa el ciclo conversacional completo:
VAD -> STT -> Cerebro Comercial (Fase 2) -> TTS -> Reproducción -> VAD

Gestiona:
1. Retención íntegra del ConversationContext entre turnos consecutivos.
2. Detección y tratamiento acotado de timeouts de silencio (timeout_no_speech).
3. Salida limpia ante orden de finalización del usuario, activación de DO_NOT_CONTACT o Ctrl+C.
4. Carga única y persistente de modelos de voz para evitar penalizaciones de latencia.
5. Limpieza de recursos y prevención de procesos huérfanos.
"""

import os
import time
import uuid
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from voice.audio_capture import (
    AudioPlaybackError,
    MicrophoneNotAvailableError,
    play_audio_file,
    record_speech_with_vad,
)
from voice.pipeline import ConversationTurnPipeline, TurnTelemetry
from voice.responder import ConversationContext
from voice.vad import VADConfig, VADState


class SessionState(str, Enum):
    """Estados del autómata de la sesión conversacional continua."""
    INITIALIZING = "initializing"
    LISTENING = "listening"
    PROCESSING = "processing"
    PLAYING = "playing"
    RETRY_WAITING = "retry_waiting"
    FINISHED = "finished"


class SessionEndReason(str, Enum):
    """Causas formales de finalización de una sesión conversacional."""
    DO_NOT_CONTACT = "do_not_contact"
    USER_EXPLICIT_EXIT = "user_explicit_exit"
    MAX_CONSECUTIVE_TIMEOUTS = "max_consecutive_timeouts"
    MAX_TURNS_REACHED = "max_turns_reached"
    KEYBOARD_INTERRUPT = "keyboard_interrupt"
    CAPTURE_ERROR = "capture_error"
    PROGRAMMATIC_STOP = "programmatic_stop"


@dataclass
class SessionConfig:
    """Configuración de la sesión conversacional continua multi-turno.
    
    Attributes:
        max_consecutive_timeouts: Número máximo de silencios iniciales antes de cerrar la sesión.
        max_turns: Límite superior opcional de turnos por sesión (None para ilimitado).
        exit_phrases: Frases que solicitan el fin de la llamada o sesión sin inventar intenciones en responder.py.
        session_output_dir: Directorio de trabajo para los archivos WAV de la sesión.
        device: Índice numérico opcional de dispositivo de audio para captura y reproducción.
        vad_config: Configuración personalizada del detector VAD (None para defaults).
        timeout_prompt_message: Mensaje del asistente cuando el usuario no responde en el turno.
        play_timeout_prompts: Si True, sintetiza y reproduce aviso al cumplirse un timeout parcial.
    """
    max_consecutive_timeouts: int = 3
    max_turns: int | None = None
    exit_phrases: tuple[str, ...] = (
        "terminar conversacion",
        "finalizar conversacion",
        "terminar llamada",
        "finalizar llamada",
        "salir de la sesion",
        "hasta luego",
        "adios",
    )
    session_output_dir: str = "output/sessions"
    device: int | None = None
    vad_config: VADConfig | None = None
    timeout_prompt_message: str = "Disculpe, no he detectado su voz. ¿Sigue ahí?"
    play_timeout_prompts: bool = True


@dataclass
class SessionTelemetry:
    """Resumen consolidado y telemetría de una sesión conversacional completa."""
    session_id: str
    total_turns: int
    consecutive_timeouts: int
    end_reason: SessionEndReason
    turns_telemetry: list[TurnTelemetry] = field(default_factory=list)
    total_wall_time_s: float = 0.0
    context: ConversationContext | None = None


def _normalize_phrase(text: str) -> str:
    """Normaliza texto para comparación tolerante a tildes y signos."""
    t = text.lower().strip()
    replacements = (
        ("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"),
        ("ü", "u"), ("ñ", "n"),
    )
    for a, b in replacements:
        t = t.replace(a, b)
    # Quitar signos de puntuación
    return "".join(c for c in t if c.isalnum() or c.isspace()).strip()


class ConversationSession:
    """Orquestador continuo de sesiones conversacionales multi-turno."""

    def __init__(
        self,
        pipeline: ConversationTurnPipeline | None = None,
        config: SessionConfig | None = None,
        capture_func: Callable[..., dict[str, Any]] | None = None,
        playback_func: Callable[..., bool] | None = None,
        on_state_change: Callable[[SessionState, str], None] | None = None,
    ):
        self.config = config if config is not None else SessionConfig()
        self.pipeline = pipeline if pipeline is not None else ConversationTurnPipeline()
        self._capture_func = capture_func if capture_func is not None else record_speech_with_vad
        self._playback_func = playback_func if playback_func is not None else play_audio_file
        self._on_state_change = on_state_change

        self.session_id: str = f"sess_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        self.session_dir: str = os.path.join(self.config.session_output_dir, self.session_id)
        self.state: SessionState = SessionState.INITIALIZING

        self._consecutive_timeouts: int = 0
        self._turns_completed: int = 0
        self._stop_requested: bool = False
        self.turns_telemetry: list[TurnTelemetry] = []

    def _set_state(self, new_state: SessionState, message: str = "") -> None:
        self.state = new_state
        if self._on_state_change is not None:
            self._on_state_change(new_state, message)

    def stop(self) -> None:
        """Solicita la interrupción limpia de la sesión en el siguiente punto seguro."""
        self._stop_requested = True

    def initialize_session(self) -> None:
        """Carga los modelos en memoria de forma persistente y prepara el directorio."""
        os.makedirs(self.session_dir, exist_ok=True)
        if not self.pipeline.is_loaded:
            self._set_state(SessionState.INITIALIZING, "Cargando modelos STT y TTS...")
            self.pipeline.load_models()

    def run(self) -> SessionTelemetry:
        """Ejecuta el bucle conversacional continuo multi-turno."""
        self.initialize_session()
        t0 = time.perf_counter()
        end_reason = SessionEndReason.PROGRAMMATIC_STOP

        print(f"\n[Sesión {self.session_id}] Iniciada. Límite de silencios: {self.config.max_consecutive_timeouts}", flush=True)

        try:
            while not self._stop_requested:
                # 1. Comprobar límite de turnos si está configurado
                if (
                    self.config.max_turns is not None
                    and self._turns_completed >= self.config.max_turns
                ):
                    end_reason = SessionEndReason.MAX_TURNS_REACHED
                    print(f"[Sesión] Alcanzado el límite configurado de {self.config.max_turns} turnos.", flush=True)
                    break

                # 2. Notificar estado de escucha
                turn_idx = self._turns_completed + 1
                input_wav = os.path.join(self.session_dir, f"turn_{turn_idx}_user.wav")
                output_wav = os.path.join(self.session_dir, f"turn_{turn_idx}_agent.wav")

                self._set_state(SessionState.LISTENING, f"Turno {turn_idx}: esperando voz del usuario...")
                print(f"\n[Sesión] (Turno {turn_idx}) Escuchando... Di tu mensaje.", flush=True)

                # 3. Capturar mediante VAD existente
                try:
                    cap_result = self._capture_func(
                        input_wav,
                        vad_config=self.config.vad_config,
                        device=self.config.device,
                    )
                except MicrophoneNotAvailableError as e:
                    print(f"[Sesión] Error de captura de audio: {e}", flush=True)
                    end_reason = SessionEndReason.CAPTURE_ERROR
                    break

                cap_state = cap_result.get("state")

                # 4. Gestión de timeout de silencio inicial
                if cap_state == VADState.TIMEOUT_NO_SPEECH.value:
                    self._consecutive_timeouts += 1
                    print(
                        f"[Sesión] Silencio detectado ({self._consecutive_timeouts}/{self.config.max_consecutive_timeouts}).",
                        flush=True,
                    )

                    if self._consecutive_timeouts >= self.config.max_consecutive_timeouts:
                        end_reason = SessionEndReason.MAX_CONSECUTIVE_TIMEOUTS
                        print("[Sesión] Máximo de silencios consecutivos alcanzado. Cerrando llamada.", flush=True)
                        break

                    # Advertencia / aviso de timeout al usuario
                    if self.config.play_timeout_prompts:
                        self._set_state(SessionState.RETRY_WAITING, "Reproduciendo aviso de reintento...")
                        timeout_wav = os.path.join(self.session_dir, f"timeout_{self._consecutive_timeouts}.wav")
                        try:
                            assert self.pipeline.piper_voice is not None
                            with wave.open(timeout_wav, "wb") as w_out:
                                self.pipeline.piper_voice.synthesize_wav(
                                    self.config.timeout_prompt_message, w_out
                                )
                            self._playback_func(timeout_wav, device=self.config.device)
                        except (OSError, RuntimeError, AudioPlaybackError, wave.Error) as ex:
                            print(f"[Sesión] Aviso de timeout no reproducido: {ex}", flush=True)

                    continue

                # Si hubo voz activa, resetear contador de silencios consecutivos
                self._consecutive_timeouts = 0

                # 5. Procesamiento STT, cerebro comercial y TTS (pipeline existente)
                self._set_state(SessionState.PROCESSING, f"Turno {turn_idx}: procesando...")

                telemetry = self.pipeline.process_turn(
                    input_wav_path=input_wav,
                    output_wav_path=output_wav,
                    context=self.pipeline.active_context,
                )
                self.turns_telemetry.append(telemetry)
                self._turns_completed += 1

                print(f"  Usuario  : \"{telemetry.transcribed_text}\"", flush=True)
                print(f"  Intención: {telemetry.intent_detected} (confianza: {telemetry.confidence})", flush=True)
                print(f"  Agente   : \"{telemetry.response_text}\"", flush=True)
                print(f"  Latencia : {telemetry.total_turnaround_ms:.1f} ms", flush=True)

                # 6. Reproducción de la respuesta generada
                self._set_state(SessionState.PLAYING, f"Turno {turn_idx}: reproduciendo respuesta...")
                self._playback_func(output_wav, device=self.config.device)

                # 7. Evaluación de condiciones de terminación
                # a) Caso DNC (No molestar / baja): cierre prioritario irreversible
                if self.pipeline.active_context.is_do_not_contact:
                    end_reason = SessionEndReason.DO_NOT_CONTACT
                    print("[Sesión] Contacto registrado como NO LLAMAR (DNC). Sesión bloqueada.", flush=True)
                    break

                # b) Orden explícita de salida por frase de terminación
                norm_user = _normalize_phrase(telemetry.transcribed_text)
                is_explicit_exit = any(
                    _normalize_phrase(phrase) in norm_user for phrase in self.config.exit_phrases
                )
                if is_explicit_exit:
                    end_reason = SessionEndReason.USER_EXPLICIT_EXIT
                    print("[Sesión] Solicitud de finalización explícita por el usuario.", flush=True)
                    break

        except KeyboardInterrupt:
            end_reason = SessionEndReason.KEYBOARD_INTERRUPT
            print("\n[Sesión] Sesión interrumpida por el usuario (Ctrl+C).", flush=True)

        finally:
            self._set_state(SessionState.FINISHED, f"Sesión finalizada ({end_reason.value})")

        wall_time = round(time.perf_counter() - t0, 3)
        print(f"[Sesión {self.session_id}] Finalizada en {wall_time} s. Turnos: {self._turns_completed}. Motivo: '{end_reason.value}'\n", flush=True)

        return SessionTelemetry(
            session_id=self.session_id,
            total_turns=self._turns_completed,
            consecutive_timeouts=self._consecutive_timeouts,
            end_reason=end_reason,
            turns_telemetry=self.turns_telemetry,
            total_wall_time_s=wall_time,
            context=self.pipeline.active_context,
        )
