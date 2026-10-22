"""Demostración interactiva de captura de audio y diálogo local (Fase 1.4).

Flujo:
1. Comprobación y diagnóstico de hardware de audio (micrófono y altavoz).
2. Captura supervisada desde micrófono (o conmutación explícita a archivo ante fallos).
3. Transcripción con faster-whisper small (CPU int8).
4. Generación de respuesta comercial determinista (responder.py).
5. Síntesis de voz con Piper davefx (CPU).
6. Reproducción directa supervisada (o entrega de archivo .wav para escucha).
7. Telemetría de latencias y reporte de incidencias.
"""

import argparse
import json
import os
import time
import wave
from dataclasses import asdict

from voice.audio_capture import (
    AudioDeviceStatus,
    MicrophoneNotAvailableError,
    check_audio_hardware,
    play_audio_file,
    record_microphone_speech,
)
from voice.pipeline import ConversationTurnPipeline, TurnTelemetry

OUTPUT_DIR = "output/mic_demo"
DEFAULT_INPUT_WAV = os.path.join(OUTPUT_DIR, "captured_speech.wav")
DEFAULT_OUTPUT_WAV = os.path.join(OUTPUT_DIR, "response_speech.wav")
RESULTS_JSON_PATH = os.path.join(OUTPUT_DIR, "mic_demo_results.json")


def run_mic_dialogue_demo(
    input_file: str | None = None,
    record_duration: float = 5.0,
    output_wav: str = DEFAULT_OUTPUT_WAV,
    device: int | None = None,
) -> dict:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 70, flush=True)
    print("DEMOSTRACIÓN DE CAPTURA POR MICRÓFONO Y DIÁLOGO LOCAL — FASE 1.4", flush=True)
    print("=" * 70, flush=True)

    # 1. Inspeccionar hardware de audio
    status: AudioDeviceStatus = check_audio_hardware(device=device)
    print(f"\n[Hardware Audio] Backend : {status.backend_name}", flush=True)
    print(f"[Hardware Audio] Micrófono: {'DISPONIBLE' if status.has_input_device else 'NO DISPONIBLE'} ({status.input_device_name or 'N/A'})", flush=True)
    print(f"[Hardware Audio] Altavoz  : {'DISPONIBLE' if status.has_output_device else 'NO DISPONIBLE'} ({status.output_device_name or 'N/A'})", flush=True)
    if device is not None:
        print(f"[Hardware Audio] Dispositivo especificado: índice {device}", flush=True)
    if status.error_detail:
        print(f"[Hardware Audio] Detalle  : {status.error_detail}", flush=True)

    capture_mode = "fallback"
    capture_duration_s = 0.0
    target_input_wav = DEFAULT_INPUT_WAV
    capture_error: str | None = None

    # 2. Obtener intervención de audio (Micrófono real, archivo provisto o fallback)
    if input_file and os.path.exists(input_file):
        capture_mode = "wav_input"
        target_input_wav = input_file
        with wave.open(target_input_wav, "rb") as wf:
            capture_duration_s = wf.getnframes() / float(wf.getframerate())
        print(f"\n[Modo Entrada] Usando archivo provisto (--input-file): {target_input_wav} ({capture_duration_s:.2f} s)", flush=True)

    elif status.has_input_device:
        target_input_wav = DEFAULT_INPUT_WAV
        print(f"\n[Modo Entrada] Intentando captura real desde el micrófono ({record_duration:.1f} s)...", flush=True)
        try:
            capture_duration_s = record_microphone_speech(
                target_input_wav,
                duration_seconds=record_duration,
                sample_rate=16000,
                device=device,
            )
            capture_mode = "physical_capture"
        except MicrophoneNotAvailableError as e:
            capture_error = str(e)
            print(f"\n[Fallo Captura Física] {e}", flush=True)
            print("  Conmutando automáticamente a intervención de prueba para continuar el pipeline...", flush=True)

    if capture_mode not in ("physical_capture", "wav_input"):
        # Activar modo fallback explícito
        capture_mode = "fallback"
        fallback_source = "output/demo_inputs/scenario_1_service_info_input.wav"
        if not os.path.exists(fallback_source):
            fallback_source = "output/audio/frase_1.wav"

        target_input_wav = fallback_source
        if os.path.exists(target_input_wav):
            with wave.open(target_input_wav, "rb") as wf:
                capture_duration_s = wf.getnframes() / float(wf.getframerate())

        print(
            f"\n[Aviso Entorno] Ejecutando demostración en modo 'fallback' con audio: "
            f"{target_input_wav} ({capture_duration_s:.2f} s)",
            flush=True,
        )

    # 3. Inicializar Pipeline
    pipeline = ConversationTurnPipeline(
        stt_model_name="small",
        stt_device="cpu",
        stt_compute_type="int8",
        tts_model_path="models/piper/es_ES-davefx-medium/es_ES-davefx-medium.onnx",
        tts_config_path="models/piper/es_ES-davefx-medium/es_ES-davefx-medium.onnx.json",
    )
    pipeline.load_models()

    # 4. Procesar turno completo
    print("\n--- PROCESANDO INTERVENCIÓN DE VOZ ---", flush=True)
    t_turn_start = time.perf_counter()
    telemetry: TurnTelemetry = pipeline.process_turn(target_input_wav, output_wav)
    time_audio_available_ms = (time.perf_counter() - t_turn_start) * 1000.0

    print(f"  Texto Reconocido : \"{telemetry.transcribed_text}\"", flush=True)
    print(f"  Intención        : {telemetry.intent_detected} (confianza: {telemetry.confidence})", flush=True)
    print(f"  Respuesta Agente : \"{telemetry.response_text}\"", flush=True)
    print(f"  Audio Generado   : {output_wav} ({telemetry.output_audio_duration_s:.2f} s)", flush=True)
    print(
        f"  Latencias        : STT: {telemetry.stt_inference_ms:.1f} ms | "
        f"Reglas: {telemetry.decision_ms:.3f} ms | "
        f"TTS: {telemetry.tts_synthesis_ms:.1f} ms | "
        f"Total Turnaround: {telemetry.total_turnaround_ms:.1f} ms",
        flush=True,
    )

    # 5. Reproducción de la respuesta
    print("\n--- REPRODUCCIÓN DEL AUDIO DE RESPUESTA ---", flush=True)
    t_play_start = time.perf_counter()
    played_successfully = play_audio_file(output_wav, device=device)
    playback_trigger_ms = (time.perf_counter() - t_play_start) * 1000.0

    # 6. Registrar resultados completos
    results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hardware_status": asdict(status),
        "capture_mode": capture_mode,
        "capture_error": capture_error,
        "input_audio_path": target_input_wav,
        "output_audio_path": output_wav,
        "metrics": {
            "capture_duration_seconds": round(capture_duration_s, 3),
            "stt_inference_ms": telemetry.stt_inference_ms,
            "decision_ms": telemetry.decision_ms,
            "tts_synthesis_ms": telemetry.tts_synthesis_ms,
            "total_turnaround_ms": telemetry.total_turnaround_ms,
            "time_to_audio_available_ms": round(time_audio_available_ms, 2),
            "playback_attempted": True,
            "playback_successful": played_successfully,
            "playback_trigger_latency_ms": round(playback_trigger_ms, 2),
            "turnaround_rtf": telemetry.turnaround_rtf,
        },
        "dialogue": {
            "transcribed_text": telemetry.transcribed_text,
            "response_text": telemetry.response_text,
            "intent_detected": telemetry.intent_detected,
            "confidence": telemetry.confidence,
        },
        "models": {
            "stt": f"{telemetry.stt_model} ({telemetry.stt_device} {telemetry.stt_compute_type})",
            "tts": telemetry.tts_model_path,
        },
    }

    with open(RESULTS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70, flush=True)
    print(f"DEMOSTRACIÓN FINALIZADA. Modo: '{capture_mode}'. Métricas en: {RESULTS_JSON_PATH}", flush=True)
    print(f"Tiempo hasta audio disponible: {time_audio_available_ms:.1f} ms", flush=True)
    print("=" * 70, flush=True)

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Demostración de diálogo por voz (Fase 1.4)")
    parser.add_argument("--input-file", type=str, default=None, help="Ruta a un archivo WAV alternativo si no se usa micrófono")
    parser.add_argument("--duration", type=float, default=5.0, help="Duración de la grabación en segundos si el micrófono está activo")
    parser.add_argument("--output-wav", type=str, default=DEFAULT_OUTPUT_WAV, help="Ruta de guardado para la respuesta de audio")
    parser.add_argument("--device", type=int, default=None, help="Índice numérico opcional del dispositivo de audio")
    args = parser.parse_args()

    run_mic_dialogue_demo(
        input_file=args.input_file,
        record_duration=args.duration,
        output_wav=args.output_wav,
        device=args.device,
    )
