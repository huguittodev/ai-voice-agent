"""Pruebas automatizadas de regresión para los componentes de STT y TTS."""

import json
import os
import wave

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def test_tts_audio_files_exist():
    """Comprueba que se han generado los 5 audios comerciales de Piper."""
    audio_dir = os.path.join(OUTPUT_DIR, "audio")
    assert os.path.exists(audio_dir), "El directorio de audio de TTS no existe"
    for i in range(1, 6):
        wav_file = os.path.join(audio_dir, f"frase_{i}.wav")
        assert os.path.exists(wav_file), f"Falta el archivo {wav_file}"
        assert os.path.getsize(wav_file) > 10000, (
            f"El archivo {wav_file} es demasiado pequeño"
        )
        with wave.open(wav_file, "rb") as wf:
            assert wf.getframerate() == 22050
            assert wf.getnchannels() == 1
            assert wf.getnframes() > 0


def test_tts_results_valid():
    """Comprueba que los resultados de benchmark TTS tienen métricas reales."""
    results_path = os.path.join(OUTPUT_DIR, "tts_results.json")
    assert os.path.exists(results_path), "Falta tts_results.json"
    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["phrases"]) == 5
    assert data["overall_rtf"] < 0.1, "El RTF de Piper en CPU debería ser < 0.10"
    assert data["total_audio_duration_seconds"] > 25.0


def test_stt_results_valid():
    """Comprueba que el benchmark STT contiene transcripciones válidas."""
    results_path = os.path.join(OUTPUT_DIR, "stt_results.json")
    assert os.path.exists(results_path), "Falta stt_results.json"
    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) >= 2
    # El modelo small en CPU debe tener resultados
    small_cpu = next(
        (
            item
            for item in data
            if item["model_name"] == "small" and item["device"] == "cpu"
        ),
        None,
    )
    assert small_cpu is not None
    assert len(small_cpu["phrases"]) == 5
    assert small_cpu["overall_rtf"] < 0.35, (
        "El RTF de small en CPU i9 debería ser < 0.35"
    )


def test_tts_sharvard_audio_files_exist():
    """Comprueba que se han generado los 5 audios comerciales de Piper con voz sharvard."""
    audio_dir = os.path.join(OUTPUT_DIR, "audio_sharvard")
    assert os.path.exists(audio_dir), "El directorio de audio de sharvard no existe"
    for i in range(1, 6):
        wav_file = os.path.join(audio_dir, f"frase_{i}.wav")
        assert os.path.exists(wav_file), f"Falta el archivo {wav_file}"
        assert os.path.getsize(wav_file) > 10000, (
            f"El archivo {wav_file} es demasiado pequeño"
        )
        with wave.open(wav_file, "rb") as wf:
            assert wf.getframerate() == 22050
            assert wf.getnchannels() == 1
            assert wf.getnframes() > 0


def test_tts_sharvard_results_valid():
    """Comprueba que los resultados de sharvard tienen métricas y licencia válidas."""
    results_path = os.path.join(OUTPUT_DIR, "tts_sharvard_results.json")
    assert os.path.exists(results_path), "Falta tts_sharvard_results.json"
    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["phrases"]) == 5
    assert data["voice_name"] == "es_ES-sharvard-medium"
    assert data["license"] == "MIT"
    assert data["overall_rtf"] < 0.1
