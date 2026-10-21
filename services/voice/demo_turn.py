"""Demostración ejecutable del ciclo de conversación de turno único (Fase 1.3).

Genera 4 casos de prueba comerciales de entrada:
1. Consulta de información sobre servicios.
2. Expresión de interés en recibir más información.
3. Propuesta de agendar una reunión.
4. Entrada ininteligible / silencio.

Ejecuta el pipeline completo y mide la latencia de cada etapa.
"""

import json
import os
import sys
import wave
from dataclasses import asdict

import numpy as np

# Asegurar que src está en el path si se ejecuta directamente
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from piper.voice import PiperVoice

from voice.pipeline import ConversationTurnPipeline, TurnTelemetry

DEMO_INPUT_DIR = "output/demo_inputs"
DEMO_OUTPUT_DIR = "output/pipeline"
RESULTS_JSON_PATH = "output/pipeline/turn_pipeline_results.json"

SCENARIOS = [
    {
        "id": "scenario_1_service_info",
        "description": "Usuario solicita información sobre servicios",
        "user_spoken_text": "Hola, buenos días, ¿qué servicios ofrecéis en vuestra empresa?",
    },
    {
        "id": "scenario_2_interest",
        "description": "Usuario muestra interés en recibir más información",
        "user_spoken_text": "Me interesa bastante la propuesta, ¿podríais enviarme más información al respecto?",
    },
    {
        "id": "scenario_3_meeting",
        "description": "Usuario propone concertar una reunión",
        "user_spoken_text": "Hola, me gustaría agendar una reunión o llamada con vosotros para el próximo jueves.",
    },
    {
        "id": "scenario_4_unintelligible",
        "description": "Entrada ininteligible (silencio o ruido de baja amplitud)",
        "user_spoken_text": "",  # Genera un audio de silencio/ruido plano
    },
]


def generate_demo_input_audios(
    tts_model_path: str = "models/piper/es_ES-davefx-medium/es_ES-davefx-medium.onnx",
    tts_config_path: str = "models/piper/es_ES-davefx-medium/es_ES-davefx-medium.onnx.json",
) -> dict:
    """Genera los archivos WAV de prueba de entrada si no existen."""
    os.makedirs(DEMO_INPUT_DIR, exist_ok=True)
    voice = None
    input_paths = {}

    for item in SCENARIOS:
        sc_id = item["id"]
        out_wav = os.path.join(DEMO_INPUT_DIR, f"{sc_id}_input.wav")
        input_paths[sc_id] = out_wav

        if os.path.exists(out_wav) and os.path.getsize(out_wav) > 0:
            continue

        text = item["user_spoken_text"]
        if text:
            if voice is None:
                print(
                    f"[Demo] Inicializando Piper para generar entradas de prueba en {DEMO_INPUT_DIR}...",
                    flush=True,
                )
                voice = PiperVoice.load(tts_model_path, config_path=tts_config_path)
            with wave.open(out_wav, "wb") as wf:
                voice.synthesize_wav(text, wf)
        else:
            # Generar audio de silencio de 1.5 segundos a 22.050 Hz (16-bit mono)
            rate = 22050
            num_samples = int(rate * 1.5)
            silence_samples = np.zeros(num_samples, dtype=np.int16)
            with wave.open(out_wav, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(rate)
                wf.writeframes(silence_samples.tobytes())

        print(
            f"  [Input Generado] {out_wav} ({os.path.getsize(out_wav)} bytes)",
            flush=True,
        )

    return input_paths


def run_single_turn_demo() -> dict:
    os.makedirs(DEMO_OUTPUT_DIR, exist_ok=True)

    print("=" * 70, flush=True)
    print("DEMOSTRACIÓN DE TURNO CONVERSACIONAL ÚNICO — FASE 1.3", flush=True)
    print(
        "Flujo: WAV Entrada -> faster-whisper (small CPU) -> Reglas -> Piper (davefx CPU) -> WAV Salida",
        flush=True,
    )
    print("=" * 70, flush=True)

    # 1. Asegurar audios de entrada
    input_wav_map = generate_demo_input_audios()

    # 2. Inicializar Pipeline
    pipeline = ConversationTurnPipeline(
        stt_model_name="small", stt_device="cpu", stt_compute_type="int8"
    )

    # 3. Cargar modelos (medición de Cold Load)
    pipeline.load_models()

    scenario_results = []

    print("\n--- EJECUTANDO CICLOS DE CONVERSACIÓN ---", flush=True)

    for i, item in enumerate(SCENARIOS, 1):
        sc_id = item["id"]
        in_wav = input_wav_map[sc_id]
        out_wav = os.path.join(DEMO_OUTPUT_DIR, f"{sc_id}_reply.wav")

        print(f"\n[Caso {i}/4] {item['description']}", flush=True)
        print(f"  Audio entrada: {in_wav}", flush=True)

        telemetry: TurnTelemetry = pipeline.process_turn(in_wav, out_wav)

        print(f'  STT Transcrito : "{telemetry.transcribed_text}"', flush=True)
        print(
            f"  Intención      : {telemetry.intent_detected} (confianza: {telemetry.confidence})",
            flush=True,
        )
        print(f'  Respuesta AI   : "{telemetry.response_text}"', flush=True)
        print(
            f"  Audio salida   : {out_wav} ({telemetry.output_audio_duration_s:.2f} s)",
            flush=True,
        )
        print(
            f"  Latencias      : STT: {telemetry.stt_inference_ms:.1f} ms | "
            f"Reglas: {telemetry.decision_ms:.3f} ms | "
            f"TTS: {telemetry.tts_synthesis_ms:.1f} ms | "
            f"TOTAL: {telemetry.total_turnaround_ms:.1f} ms",
            flush=True,
        )
        print(
            f"  Turnaround RTF : {telemetry.turnaround_rtf:.4f} (Proceso {(1.0 / telemetry.turnaround_rtf if telemetry.turnaround_rtf > 0 else 0):.1f}x más rápido que audio entrada)",
            flush=True,
        )

        scenario_results.append(
            {
                "scenario_id": sc_id,
                "description": item["description"],
                "telemetry": asdict(telemetry),
            }
        )

    # Resumen y métricas globales
    warm_turns = scenario_results[1:] if len(scenario_results) > 1 else scenario_results
    avg_stt_ms = np.mean([r["telemetry"]["stt_inference_ms"] for r in scenario_results])
    avg_tts_ms = np.mean([r["telemetry"]["tts_synthesis_ms"] for r in scenario_results])
    avg_total_ms = np.mean(
        [r["telemetry"]["total_turnaround_ms"] for r in scenario_results]
    )

    summary_data = {
        "cold_load": {
            "stt_cold_load_ms": round(pipeline.cold_load_stt_ms, 2),
            "tts_cold_load_ms": round(pipeline.cold_load_tts_ms, 2),
            "total_cold_load_ms": round(
                pipeline.cold_load_stt_ms + pipeline.cold_load_tts_ms, 2
            ),
        },
        "averages_turnaround": {
            "avg_stt_ms": round(avg_stt_ms, 2),
            "avg_tts_ms": round(avg_tts_ms, 2),
            "avg_decision_ms": round(
                np.mean([r["telemetry"]["decision_ms"] for r in scenario_results]), 4
            ),
            "avg_total_turnaround_ms": round(avg_total_ms, 2),
        },
        "scenarios": scenario_results,
    }

    with open(RESULTS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70, flush=True)
    print("DEMOSTRACIÓN FINALIZADA EXITOSAMENTE.", flush=True)
    print(f"Resultados guardados en: {RESULTS_JSON_PATH}", flush=True)
    print(
        f"Latencia media de turno (Turnaround Time): {avg_total_ms:.1f} ms", flush=True
    )
    print("=" * 70, flush=True)

    return summary_data


if __name__ == "__main__":
    run_single_turn_demo()
