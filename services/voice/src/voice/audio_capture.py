"""Módulo de captura y reproducción de audio local para la Fase 1.4.

Proporciona captura y reproducción de audio supervisada por procesos hijos independientes
para prevenir bloqueos indefinidos del hilo principal ante inanición de muestras o bloqueos
nativos de PortAudio/WSLg.
"""

import multiprocessing
import os
import shutil
import subprocess
import time
import wave
from dataclasses import dataclass, field
from typing import Any

from voice.vad import EnergyVoiceActivityDetector, VADConfig, VADState


class AudioHardwareError(Exception):
    """Excepción base para incidencias con dispositivos de audio."""


class MicrophoneNotAvailableError(AudioHardwareError):
    """Dispositivo de entrada de audio no disponible, incompatible o sin muestras."""


class AudioPlaybackError(AudioHardwareError):
    """Dispositivo de salida de audio no disponible o bloqueado durante reproducción."""


@dataclass
class AudioDeviceStatus:
    has_input_device: bool
    has_output_device: bool
    backend_name: str
    input_device_name: str | None
    output_device_name: str | None
    error_detail: str | None
    default_input_index: int | None = None
    default_output_index: int | None = None
    available_devices: list[dict[str, Any]] = field(default_factory=list)


def check_audio_hardware(device: int | None = None) -> AudioDeviceStatus:
    """Verifica la presencia y accesibilidad de dispositivos de captura y reproducción.
    
    Si se especifica `device`, comprueba explícitamente dicho dispositivo como entrada.
    """
    try:
        import sounddevice as sd  # type: ignore

        devices = sd.query_devices()
        dev_list = [dict(d) for d in devices]

        input_dev = None
        output_dev = None
        default_in_idx = None
        default_out_idx = None

        default_in, default_out = sd.default.device

        # Si se solicita un dispositivo específico
        if device is not None:
            if 0 <= device < len(devices):
                d_info = devices[device]
                if d_info.get("max_input_channels", 0) > 0:
                    input_dev = d_info.get("name")
                    default_in_idx = device
                else:
                    return AudioDeviceStatus(
                        has_input_device=False,
                        has_output_device=False,
                        backend_name="sounddevice (PortAudio)",
                        input_device_name=None,
                        output_device_name=None,
                        error_detail=f"El dispositivo con índice {device} no tiene canales de entrada.",
                        available_devices=dev_list,
                    )
            else:
                return AudioDeviceStatus(
                    has_input_device=False,
                    has_output_device=False,
                    backend_name="sounddevice (PortAudio)",
                    input_device_name=None,
                    output_device_name=None,
                    error_detail=f"Índice de dispositivo inválido: {device}. Total disponibles: {len(devices)}.",
                    available_devices=dev_list,
                )
        else:
            if default_in is not None and default_in >= 0:
                dev_info = sd.query_devices(default_in, "input")
                if dev_info.get("max_input_channels", 0) > 0:
                    input_dev = dev_info.get("name")
                    default_in_idx = default_in

        if default_out is not None and default_out >= 0:
            dev_info = sd.query_devices(default_out, "output")
            if dev_info.get("max_output_channels", 0) > 0:
                output_dev = dev_info.get("name")
                default_out_idx = default_out

        # Si no había default_in pero hay dispositivos, buscar el primer candidato con canales de entrada
        if input_dev is None and device is None:
            for idx, d in enumerate(devices):
                if d.get("max_input_channels", 0) > 0:
                    input_dev = d.get("name")
                    default_in_idx = idx
                    break

        if output_dev is None:
            for idx, d in enumerate(devices):
                if d.get("max_output_channels", 0) > 0:
                    output_dev = d.get("name")
                    default_out_idx = idx
                    break

        has_in = input_dev is not None
        has_out = output_dev is not None

        return AudioDeviceStatus(
            has_input_device=has_in,
            has_output_device=has_out,
            backend_name="sounddevice (PortAudio)",
            input_device_name=input_dev,
            output_device_name=output_dev,
            default_input_index=default_in_idx,
            default_output_index=default_out_idx,
            error_detail=None if (has_in and has_out) else "Dispositivo de audio predeterminado no asignado",
            available_devices=dev_list,
        )

    except ImportError:
        return AudioDeviceStatus(
            has_input_device=False,
            has_output_device=False,
            backend_name="none",
            input_device_name=None,
            output_device_name=None,
            error_detail="La librería 'sounddevice' no está instalada en el entorno.",
            available_devices=[],
        )
    except OSError as e:
        err_msg = str(e)
        if "PortAudio library not found" in err_msg:
            detail = (
                "La biblioteca del sistema 'libportaudio.so.2' no está presente en el entorno Linux/WSL2. "
                "En Ubuntu/Debian se instala con: sudo apt install libportaudio2"
            )
        else:
            detail = f"Error al inicializar PortAudio/sounddevice: {err_msg}"

        return AudioDeviceStatus(
            has_input_device=False,
            has_output_device=False,
            backend_name="sounddevice (sin PortAudio)",
            input_device_name=None,
            output_device_name=None,
            error_detail=detail,
            available_devices=[],
        )


def _worker_record_process(
    output_wav_path: str,
    duration_seconds: float,
    sample_rate: int,
    channels: int,
    device: int | None,
    result_queue: Any,
) -> None:
    """Función de captura ejecutada dentro de un subproceso aislado.
    
    Protege al proceso principal de cualquier congelación a nivel de C/PortAudio.
    """
    try:
        import numpy as np
        import sounddevice as sd  # type: ignore

        # 1. Validar dispositivo
        if device is not None:
            dev_info = sd.query_devices(device, "input")
            target_device = device
        else:
            def_in = sd.default.device[0]
            if def_in is None or def_in < 0:
                result_queue.put({
                    "success": False,
                    "error": "No hay dispositivo de entrada predeterminado configurado.",
                })
                return
            dev_info = sd.query_devices(def_in, "input")
            target_device = def_in

        max_in = dev_info.get("max_input_channels", 0)
        if max_in < 1:
            result_queue.put({
                "success": False,
                "error": f"El dispositivo {target_device} ('{dev_info.get('name')}') no tiene canales de entrada.",
            })
            return

        # Ajustar canales si el hardware no soporta los solicitados
        actual_channels = min(channels, max_in)

        num_frames = int(duration_seconds * sample_rate)
        frames_captured: list[np.ndarray] = []
        stream_errors: list[str] = []

        def audio_callback(indata, _frames, _time_info, status):
            if status:
                stream_errors.append(str(status))
            frames_captured.append(indata.copy())

        t0 = time.perf_counter()
        with sd.InputStream(
            device=target_device,
            channels=actual_channels,
            samplerate=sample_rate,
            dtype="int16",
            callback=audio_callback,
        ):
            # Límite interno de espera: duración solicitada + 1.2 segundos de margen
            deadline = time.perf_counter() + duration_seconds + 1.2
            while time.perf_counter() < deadline:
                current_samples = sum(len(chunk) for chunk in frames_captured)
                if current_samples >= num_frames:
                    break
                time.sleep(0.02)

        actual_duration = time.perf_counter() - t0

        if not frames_captured:
            result_queue.put({
                "success": False,
                "error": (
                    f"Inanición de muestras: 0 datos recibidos del dispositivo {target_device} "
                    f"('{dev_info.get('name')}'). Posible bloqueo de permisos en WSLg/Windows."
                ),
            })
            return

        audio_data = np.concatenate(frames_captured, axis=0)[:num_frames]
        max_amp = int(np.max(np.abs(audio_data)))
        rms = float(np.sqrt(np.mean(audio_data.astype(np.float32) ** 2)))

        os.makedirs(os.path.dirname(output_wav_path) or ".", exist_ok=True)
        with wave.open(output_wav_path, "wb") as wf:
            wf.setnchannels(actual_channels)
            wf.setsampwidth(2)  # 16-bit PCM = 2 bytes
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data.tobytes())

        result_queue.put({
            "success": True,
            "duration": actual_duration,
            "max_amp": max_amp,
            "rms": rms,
            "channels": actual_channels,
            "device_name": dev_info.get("name"),
            "errors": stream_errors,
        })

    except (OSError, RuntimeError, ValueError) as e:
        result_queue.put({
            "success": False,
            "error": f"Error en flujo de captura: {e}",
        })


def record_microphone_speech(
    output_wav_path: str,
    duration_seconds: float = 5.0,
    sample_rate: int = 16000,
    channels: int = 1,
    device: int | None = None,
    timeout_seconds: float | None = None,
) -> float:
    """Captura audio del micrófono por una duración fija y lo guarda en formato WAV PCM 16-bit.
    
    Aísla la captura en un proceso hijo supervisado con tiempo límite estricto para evitar
    que una llamada nativa bloqueada congele el proceso principal.
    """
    status = check_audio_hardware(device=device)
    if not status.has_input_device:
        raise MicrophoneNotAvailableError(
            f"No se puede capturar audio del micrófono: {status.error_detail or 'Dispositivo no encontrado'}"
        )

    # Tiempo límite global para el proceso hijo
    effective_timeout = timeout_seconds if timeout_seconds is not None else (duration_seconds + 2.5)

    ctx = multiprocessing.get_context("spawn")
    result_queue = ctx.Queue()

    proc = ctx.Process(
        target=_worker_record_process,
        args=(
            output_wav_path,
            duration_seconds,
            sample_rate,
            channels,
            device if device is not None else status.default_input_index,
            result_queue,
        ),
    )

    print(f"[Micrófono] Grabando {duration_seconds:.1f} s a {sample_rate} Hz (timeout máx: {effective_timeout:.1f} s)...", flush=True)
    t0 = time.perf_counter()
    proc.start()
    proc.join(timeout=effective_timeout)

    if proc.is_alive():
        print(f"  [Aviso] Timeout alcanzado ({effective_timeout:.1f} s). Cancelando subproceso de captura...", flush=True)
        proc.terminate()
        proc.join(timeout=1.0)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=0.5)

        raise MicrophoneNotAvailableError(
            f"Captura cancelada por timeout ({effective_timeout:.1f} s): el dispositivo "
            f"(índice {device if device is not None else status.default_input_index}) no entregó muestras a tiempo."
        )

    if not result_queue.empty():
        result = result_queue.get()
        if not result.get("success"):
            raise MicrophoneNotAvailableError(result.get("error", "Error no especificado durante la captura."))

        max_amp = result.get("max_amp", 0)
        rms = result.get("rms", 0.0)
        if max_amp == 0:
            print("  [Aviso] La señal grabada es silencio plano (amplitud = 0).", flush=True)

        print(
            f"[Micrófono] Audio guardado en {output_wav_path} "
            f"(amplitud máx: {max_amp}, RMS: {rms:.1f}, dispositivo: '{result.get('device_name')}')",
            flush=True,
        )
        return float(result.get("duration", time.perf_counter() - t0))

    exit_code = proc.exitcode
    raise MicrophoneNotAvailableError(
        f"El proceso de captura terminó abruptamente sin devolver telemetría (código de salida: {exit_code})."
    )


def _worker_vad_record_process(
    output_wav_path: str,
    vad_config: VADConfig,
    channels: int,
    device: int | None,
    result_queue: Any,
) -> None:
    """Función de captura supervisada por VAD ejecutada en un subproceso aislado."""
    try:
        import sounddevice as sd  # type: ignore

        if device is not None:
            dev_info = sd.query_devices(device, "input")
            target_device = device
        else:
            def_in = sd.default.device[0]
            if def_in is None or def_in < 0:
                result_queue.put({
                    "success": False,
                    "error": "No hay dispositivo de entrada predeterminado configurado.",
                })
                return
            dev_info = sd.query_devices(def_in, "input")
            target_device = def_in

        max_in = dev_info.get("max_input_channels", 0)
        if max_in < 1:
            result_queue.put({
                "success": False,
                "error": f"El dispositivo {target_device} ('{dev_info.get('name')}') no tiene canales de entrada.",
            })
            return

        actual_channels = min(channels, max_in)
        detector = EnergyVoiceActivityDetector(vad_config)
        stream_errors: list[str] = []
        terminal_states = (
            VADState.SPEECH_ENDED,
            VADState.TIMEOUT_NO_SPEECH,
            VADState.MAX_DURATION_REACHED,
        )

        def audio_callback(indata, _frames, _time_info, status):
            if status:
                stream_errors.append(str(status))
            mono_chunk = indata[:, 0] if indata.ndim > 1 else indata
            detector.process_chunk(mono_chunk)

        t0 = time.perf_counter()
        max_deadline = t0 + vad_config.max_utterance_duration_s + vad_config.initial_silence_timeout_s + 2.0

        with sd.InputStream(
            device=target_device,
            channels=actual_channels,
            samplerate=vad_config.sample_rate,
            blocksize=vad_config.chunk_size_samples,
            dtype="int16",
            callback=audio_callback,
        ):
            while time.perf_counter() < max_deadline:
                if detector.state in terminal_states:
                    break
                time.sleep(0.01)

        actual_duration = time.perf_counter() - t0
        res = detector.get_consolidated_result()

        if len(res.audio_pcm) > 0 and res.state in (VADState.SPEECH_ENDED, VADState.MAX_DURATION_REACHED):
            os.makedirs(os.path.dirname(output_wav_path) or ".", exist_ok=True)
            with wave.open(output_wav_path, "wb") as wf:
                wf.setnchannels(actual_channels)
                wf.setsampwidth(2)
                wf.setframerate(vad_config.sample_rate)
                wf.writeframes(res.audio_pcm.tobytes())

        result_queue.put({
            "success": True,
            "state": res.state.value,
            "duration_seconds": res.duration_seconds,
            "elapsed_seconds": actual_duration,
            "speech_start_ms": res.speech_start_ms,
            "speech_end_ms": res.speech_end_ms,
            "total_speech_duration_ms": res.total_speech_duration_ms,
            "peak_rms": res.peak_rms,
            "chunks_processed": res.chunks_processed,
            "device_name": dev_info.get("name"),
            "errors": stream_errors,
        })

    except (OSError, RuntimeError, ValueError) as e:
        result_queue.put({
            "success": False,
            "error": f"Error en flujo de captura con VAD: {e}",
        })


def record_speech_with_vad(
    output_wav_path: str,
    vad_config: VADConfig | None = None,
    channels: int = 1,
    device: int | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Captura voz delimitada dinámicamente por silencio mediante VAD en un subproceso aislado.
    
    Inicia la captura cuando detecta habla y la finaliza tras el silencio configurado
    (silence_hangover_ms). Si no se detecta habla dentro de initial_silence_timeout_s,
    retorna con estado timeout_no_speech sin error crítico.
    """
    cfg = vad_config if vad_config is not None else VADConfig()
    status = check_audio_hardware(device=device)
    if not status.has_input_device:
        raise MicrophoneNotAvailableError(
            f"No se puede capturar audio del micrófono: {status.error_detail or 'Dispositivo no encontrado'}"
        )

    effective_timeout = timeout_seconds if timeout_seconds is not None else (
        cfg.max_utterance_duration_s + cfg.initial_silence_timeout_s + 3.0
    )

    ctx = multiprocessing.get_context("spawn")
    result_queue = ctx.Queue()

    proc = ctx.Process(
        target=_worker_vad_record_process,
        args=(
            output_wav_path,
            cfg,
            channels,
            device if device is not None else status.default_input_index,
            result_queue,
        ),
    )

    t0 = time.perf_counter()
    proc.start()
    proc.join(timeout=effective_timeout)

    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=1.0)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=0.5)

        raise MicrophoneNotAvailableError(
            f"Captura con VAD cancelada por timeout de seguridad ({effective_timeout:.1f} s)."
        )

    if not result_queue.empty():
        result = result_queue.get()
        if not result.get("success"):
            raise MicrophoneNotAvailableError(result.get("error", "Error no especificado durante captura VAD."))

        result["total_wall_time_s"] = round(time.perf_counter() - t0, 3)
        return result

    exit_code = proc.exitcode
    raise MicrophoneNotAvailableError(
        f"El subproceso de captura VAD terminó abruptamente sin telemetría (código: {exit_code})."
    )


def _worker_play_process(
    wav_path: str,
    device: int | None,
    result_queue: Any,
) -> None:
    """Función de reproducción ejecutada en un subproceso aislado."""
    try:
        import sounddevice as sd  # type: ignore
        import soundfile as sf  # type: ignore

        data, fs = sf.read(wav_path, dtype="float32")
        duration = len(data) / float(fs)

        target_device = device if device is not None else (
            sd.default.device[1] if (sd.default.device[1] is not None and sd.default.device[1] >= 0) else None
        )

        t0 = time.perf_counter()
        sd.play(data, samplerate=fs, device=target_device)
        deadline = t0 + duration + 0.3
        while time.perf_counter() < deadline:
            if not sd.get_stream().active:
                break
            time.sleep(0.04)

        if sd.get_stream().active:
            sd.stop()

        result_queue.put({"success": True})

    except (OSError, RuntimeError) as e:
        result_queue.put({"success": False, "error": str(e)})


def play_audio_file(
    wav_path: str,
    device: int | None = None,
    timeout_seconds: float | None = None,
) -> bool:
    """Intenta reproducir un archivo de audio mediante sounddevice o herramientas de sistema.
    
    Aísla la reproducción en un subproceso con timeout para no bloquear el proceso llamador.
    """
    if not os.path.exists(wav_path):
        raise FileNotFoundError(f"Archivo de audio no encontrado: {wav_path}")

    # Obtener duración del archivo para calibrar timeout
    try:
        with wave.open(wav_path, "rb") as wf:
            wav_duration = wf.getnframes() / float(wf.getframerate())
    except (wave.Error, OSError):
        wav_duration = 3.0

    status = check_audio_hardware(device=device)
    if status.has_output_device:
        effective_timeout = timeout_seconds if timeout_seconds is not None else (wav_duration + 3.0)
        ctx = multiprocessing.get_context("spawn")
        result_queue = ctx.Queue()

        proc = ctx.Process(
            target=_worker_play_process,
            args=(wav_path, device if device is not None else status.default_output_index, result_queue),
        )

        try:
            print(f"[Altavoz] Intentando reproducción con sounddevice ({wav_path}, max {effective_timeout:.1f} s)...", flush=True)
            proc.start()
            proc.join(timeout=effective_timeout)

            if proc.is_alive():
                print(f"  [Aviso] Timeout de reproducción alcanzado ({effective_timeout:.1f} s). Cancelando subproceso...", flush=True)
                proc.terminate()
                proc.join(timeout=0.5)
                if proc.is_alive():
                    proc.kill()
                    proc.join(timeout=0.5)
            elif not result_queue.empty():
                res = result_queue.get()
                if res.get("success"):
                    print("[Altavoz] Reproducción finalizada con éxito.", flush=True)
                    return True
                print(f"  [Aviso] Falló reproducción: {res.get('error')}", flush=True)
        except (multiprocessing.ProcessError, OSError) as e:
            print(f"  [Aviso] Error gestionando subproceso de reproducción: {e}", flush=True)

    # Si sounddevice falló o no está disponible, intentar herramientas CLI del sistema con timeout explícito
    for player in ["paplay", "pw-play", "aplay", "ffplay"]:
        if shutil.which(player):
            try:
                print(f"[Altavoz] Reproduciendo mediante herramienta {player}...", flush=True)
                subprocess.run(
                    [player, wav_path],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=wav_duration + 3.0,
                )
                return True
            except subprocess.SubprocessError:
                pass

    print(f"[Altavoz] Reproductor directo no disponible. Archivo listo para escucha en: {wav_path}", flush=True)
    return False
