"""Benchmark de síntesis de voz (TTS) con Piper en español peninsular."""

import json
import os
import sys
import time
import wave

import psutil
from piper.voice import PiperVoice

PHRASES = [
    {
        "id": "frase_1",
        "category": "Saludo y propuesta comercial",
        "text": "Buenos días, le llamo de Soluciones Cloud para presentarle nuestra herramienta de automatización para equipos comerciales.",
    },
    {
        "id": "frase_2",
        "category": "Cifras, porcentajes y fechas",
        "text": "Hemos ayudado a más de 150 empresas del sector a reducir un 35% sus costes operativos durante el primer trimestre de 2026.",
    },
    {
        "id": "frase_3",
        "category": "Marcas y anglicismos tecnológicos",
        "text": "Nuestra solución se integra de forma nativa con Salesforce, HubSpot y Microsoft Dynamics mediante APIs seguras.",
    },
    {
        "id": "frase_4",
        "category": "Objeción y agendamiento de reunión",
        "text": "Entiendo perfectamente que ahora mismo no tengan presupuesto; ¿le parece si lo comentamos brevemente el próximo jueves a las 11:30?",
    },
    {
        "id": "frase_5",
        "category": "Complejidad técnica y fonética",
        "text": "Implementamos arquitecturas híbridas optimizadas sobre microservicios con cifrado de extremo a extremo sin interrumpir su operativa.",
    },
]


def run_tts_benchmark(
    model_path: str = "models/piper/es_ES-davefx-medium/es_ES-davefx-medium.onnx",
    config_path: str = "models/piper/es_ES-davefx-medium/es_ES-davefx-medium.onnx.json",
    output_dir: str = "output/audio",
    results_json: str = "output/tts_results.json",
):
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.dirname(results_json), exist_ok=True)

    process = psutil.Process()
    ram_initial_mb = process.memory_info().rss / (1024 * 1024)

    print("=" * 60, flush=True)
    print("INICIANDO BENCHMARK TTS — PIPER (es_ES-davefx-medium)", flush=True)
    print(f"Modelo ONNX: {model_path}", flush=True)
    print(f"RAM inicial proceso: {ram_initial_mb:.2f} MB", flush=True)
    print("=" * 60, flush=True)

    # 1. Medir tiempo de carga del modelo (Cold Load)
    t0 = time.perf_counter()
    voice = PiperVoice.load(model_path, config_path=config_path)
    cold_load_time_ms = (time.perf_counter() - t0) * 1000.0
    ram_after_load_mb = process.memory_info().rss / (1024 * 1024)

    print(f"Tiempo de carga del modelo: {cold_load_time_ms:.2f} ms", flush=True)
    print(
        f"RAM tras cargar modelo: {ram_after_load_mb:.2f} MB (Delta: {ram_after_load_mb - ram_initial_mb:.2f} MB)",
        flush=True,
    )

    results = {
        "model_path": model_path,
        "config_path": config_path,
        "voice_name": "es_ES-davefx-medium",
        "license": "CC0 1.0 Universal (Public Domain)",
        "sample_rate_hz": voice.config.sample_rate,
        "cold_load_time_ms": round(cold_load_time_ms, 2),
        "ram_initial_mb": round(ram_initial_mb, 2),
        "ram_after_load_mb": round(ram_after_load_mb, 2),
        "phrases": [],
    }

    total_audio_duration = 0.0
    total_synthesis_time = 0.0

    # 2. Generar síntesis para cada frase
    for item in PHRASES:
        phrase_id = item["id"]
        text = item["text"]
        out_wav = os.path.join(output_dir, f"{phrase_id}.wav")

        # Medir tiempo de síntesis
        t_start = time.perf_counter()
        with wave.open(out_wav, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)
        synth_time_s = time.perf_counter() - t_start
        synth_time_ms = synth_time_s * 1000.0

        # Medir duración del audio resultante
        with wave.open(out_wav, "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            duration_s = frames / float(rate)
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            file_bytes = os.path.getsize(out_wav)

        rtf = synth_time_s / duration_s if duration_s > 0 else 0.0
        total_audio_duration += duration_s
        total_synthesis_time += synth_time_s

        phrase_res = {
            "id": phrase_id,
            "category": item["category"],
            "text": text,
            "output_file": out_wav,
            "file_bytes": file_bytes,
            "duration_seconds": round(duration_s, 3),
            "synthesis_time_ms": round(synth_time_ms, 2),
            "rtf": round(rtf, 4),
            "sample_rate": rate,
            "channels": channels,
            "sample_width_bytes": sample_width,
        }
        results["phrases"].append(phrase_res)

        print(
            f"[{phrase_id}] Síntesis: {synth_time_ms:.1f} ms | Duración: {duration_s:.2f} s | RTF: {rtf:.4f} | Archivo: {out_wav}",
            flush=True,
        )

    ram_final_mb = process.memory_info().rss / (1024 * 1024)
    overall_rtf = (
        total_synthesis_time / total_audio_duration if total_audio_duration > 0 else 0.0
    )
    results["ram_final_mb"] = round(ram_final_mb, 2)
    results["total_audio_duration_seconds"] = round(total_audio_duration, 3)
    results["total_synthesis_time_seconds"] = round(total_synthesis_time, 3)
    results["overall_rtf"] = round(overall_rtf, 4)

    with open(results_json, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("=" * 60, flush=True)
    print("BENCHMARK TTS COMPLETADO: 5 frases generadas.", flush=True)
    print(
        f"Duración total audio: {total_audio_duration:.2f} s | Tiempo total síntesis: {total_synthesis_time * 1000:.1f} ms",
        flush=True,
    )
    print(
        f"RTF Global: {overall_rtf:.4f} (Inferencia {(1.0 / overall_rtf):.1f}x más rápida que tiempo real)",
        flush=True,
    )
    print(f"Resultados guardados en: {results_json}", flush=True)
    print("=" * 60, flush=True)
    return results


if __name__ == "__main__":
    voice_choice = sys.argv[1] if len(sys.argv) > 1 else "davefx"
    if voice_choice == "sharvard":
        run_tts_benchmark(
            model_path="models/piper/es_ES-sharvard-medium/es_ES-sharvard-medium.onnx",
            config_path="models/piper/es_ES-sharvard-medium/es_ES-sharvard-medium.onnx.json",
            output_dir="output/audio_sharvard",
            results_json="output/tts_sharvard_results.json",
        )
    else:
        run_tts_benchmark()
