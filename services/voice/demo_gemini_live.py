"""Punto de entrada para el prototipo experimental de voz natural con Gemini Live API.

Permite conversar directamente por audio en tiempo real usando el micrófono y los
altavoces del ordenador, con speech-to-speech nativo y baja latencia.

Uso:
  export GEMINI_API_KEY="tu-clave-aqui"
  uv run python demo_gemini_live.py
  uv run python demo_gemini_live.py --model gemini-2.0-flash-exp --voice Puck
"""

import argparse
import asyncio
import logging
import os
import sys

from voice.audio_capture import check_audio_hardware
from voice.gemini_live import (
    DEFAULT_LIVE_MODEL,
    DEFAULT_LIVE_VOICE,
    FREE_TIER_PRIVACY_WARNING,
    GeminiLiveConfig,
    GeminiLiveConfigError,
    GeminiLiveConnectionError,
    GeminiLiveQuotaError,
    GeminiLiveSession,
    LiveCommercialState,
    list_available_models,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prototipo experimental de conversación por voz con Gemini Live API"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("GEMINI_LIVE_MODEL", DEFAULT_LIVE_MODEL),
        help=f"Identificador del modelo multimodal (por defecto: {DEFAULT_LIVE_MODEL})",
    )
    parser.add_argument(
        "--voice",
        type=str,
        default=os.getenv("GEMINI_LIVE_VOICE", DEFAULT_LIVE_VOICE),
        help=f"Voz predefinida de Gemini (por defecto: {DEFAULT_LIVE_VOICE})",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="Consulta y muestra los modelos disponibles para la clave configurada",
    )
    parser.add_argument(
        "--input-device",
        type=int,
        default=None,
        help="Índice del dispositivo de entrada (micrófono)",
    )
    parser.add_argument(
        "--output-device",
        type=int,
        default=None,
        help="Índice del dispositivo de salida (altavoz)",
    )
    parser.add_argument(
        "--max-duration",
        type=float,
        default=900.0,
        help="Duración máxima de la sesión en segundos (por defecto: 900s / 15min)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Activa logs detallados de depuración",
    )
    return parser.parse_args()


def setup_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def print_banner(config: GeminiLiveConfig) -> None:
    print("=" * 75)
    print("PROTOTIPO DE VOZ NATURAL EN TIEMPO REAL — GEMINI MULTIMODAL LIVE API")
    print("=" * 75)
    print(f"Modelo seleccionado : {config.model}")
    print(f"Voz predefinida     : {config.voice_name}")
    print(f"Frecuencia entrada  : {config.sample_rate_in} Hz (PCM 16-bit mono)")
    print(f"Frecuencia salida   : {config.sample_rate_out} Hz (PCM 24-bit mono)")
    print(f"Tarifa base oficial : {int(config.base_price_eur)} €")
    print("-" * 75)
    print(FREE_TIER_PRIVACY_WARNING)
    print("-" * 75)


def check_environment_and_hardware(args: argparse.Namespace) -> GeminiLiveConfig:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("\n❌ ERROR: Falta la variable de entorno GEMINI_API_KEY.")
        print("Para configurarla de forma segura en tu sesión de WSL2:")
        print("  export GEMINI_API_KEY=\"AIzaSy...\"")
        print("\nO añade la clave temporalmente antes de ejecutar:")
        print("  GEMINI_API_KEY=\"AIzaSy...\" uv run python demo_gemini_live.py\n")
        sys.exit(1)

    hw = check_audio_hardware(device=args.input_device)
    print(f"[Hardware] Micrófono: {'DISPONIBLE' if hw.has_input_device else 'NO DISPONIBLE'} ({hw.input_device_name or 'N/A'})")
    print(f"[Hardware] Altavoz  : {'DISPONIBLE' if hw.has_output_device else 'NO DISPONIBLE'} ({hw.output_device_name or 'N/A'})")

    if not hw.has_input_device:
        print("\n[Advertencia] No se detectó micrófono de entrada. Comprueba la configuración de audio de WSL2.")

    return GeminiLiveConfig(
        api_key=api_key,
        model=args.model,
        voice_name=args.voice,
        input_device=args.input_device,
        output_device=args.output_device,
        max_session_duration_s=args.max_duration,
    )


def print_instructions() -> None:
    print("\nINSTRUCCIONES DE CONVERSACIÓN:")
    print("- Habla con normalidad a través de tu micrófono.")
    print("- El agente responde con voz fluida y natural en español.")
    print("- Soporta INTERRUPCIÓN (barge-in): Si comienzas a hablar mientras el")
    print("  asistente habla, se callará de inmediato para escucharte.")
    print("- Puedes probar:")
    print("  * «¿Cuánto cuesta la página web?»")
    print("  * «Pásame con Hugo»")
    print("  * «No me interesa, muchas gracias»")
    print("  * «No me llaméis más / borrad mi contacto» (activa DNC determinista)")
    print("- Pulsa Ctrl+C en cualquier momento para finalizar limpiamente.\n")
    print("Iniciando conexión con Gemini Live API...\n")


async def async_main() -> int:
    args = parse_arguments()
    setup_logging(args.debug)

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("\n❌ ERROR: Falta la variable de entorno GEMINI_API_KEY.")
        print("Para configurarla de forma segura en tu sesión de WSL2:")
        print("  export GEMINI_API_KEY=\"AIzaSy...\"")
        print("\nO añade la clave temporalmente antes de ejecutar:")
        print("  GEMINI_API_KEY=\"AIzaSy...\" uv run python demo_gemini_live.py\n")
        return 1

    if args.list_models:
        print("Consultando modelos disponibles en Google AI Studio para tu clave de API...")
        try:
            models = list_available_models(api_key)
            print(f"\nModelos encontrados ({len(models)}):")
            for m in models:
                indicator = " [Soporta Live/Audio]" if ("live" in m.lower() or "flash" in m.lower()) else ""
                print(f"  - {m}{indicator}")
            print("\nPuedes seleccionar cualquiera de ellos usando: --model <nombre_modelo>")
            return 0
        except Exception as exc:
            print(f"\n❌ Error consultando modelos: {exc}")
            return 1

    config = check_environment_and_hardware(args)
    print_banner(config)
    print_instructions()

    state = LiveCommercialState()
    session = GeminiLiveSession(config=config, state=state)

    try:
        metrics = await session.run()
    except GeminiLiveQuotaError as qerr:
        print("\n[CLASIFICACIÓN: LÍMITE DE CUOTA]")
        print(f"Detalle: {qerr}")
        return 2
    except GeminiLiveConfigError as cfgerr:
        print("\n[CLASIFICACIÓN: CONFIGURACIÓN O AUTENTICACIÓN INVÁLIDA]")
        print(f"Detalle: {cfgerr}")
        return 1
    except GeminiLiveConnectionError as connerr:
        err_msg = str(connerr)
        print("\n[CLASIFICACIÓN: FALLO DE CONEXIÓN O MODELO]")
        if "404" in err_msg or "NOT_FOUND" in err_msg or "is not found" in err_msg or "does not exist" in err_msg:
            print(f"Causa: El modelo '{config.model}' no existe o no está habilitado para tu cuenta.")
            print("Sugerencia: Ejecuta con '--list-models' para ver qué modelos tiene asignados tu clave:")
            print("  uv run python demo_gemini_live.py --list-models")
        elif "403" in err_msg or "PERMISSION_DENIED" in err_msg:
            print("Causa: Clave de API rechazada por permisos. Verifica que la clave tenga acceso al Live API.")
        else:
            print(f"Detalle técnico: {connerr}")
        return 3
    except KeyboardInterrupt:
        print("\n\nSesión interrumpida por el usuario.")
        metrics = session.metrics

    print("\n" + "=" * 75)
    print("RESUMEN DE LA SESIÓN LIVE:")
    print(f"- Duración total       : {metrics.duration_s:.1f} segundos")
    print(f"- Turnos completados   : {metrics.turns_completed}")
    print(f"- Interrupciones usuario: {metrics.interruption_count}")
    print(f"- Datos enviados (mic) : {metrics.bytes_sent / 1024:.1f} KB")
    print(f"- Datos recibidos (voz): {metrics.bytes_received / 1024:.1f} KB")
    print(f"- Causa de terminación : {metrics.end_reason}")
    if metrics.tools_invoked:
        print(f"- Herramientas llamadas: {', '.join(metrics.tools_invoked)}")
    print("-" * 75)
    print("ESTADO COMERCIAL FINAL (CONTROL DETERMINISTA):")
    print(f"- Interés expresado    : {'SÍ' if state.interest_expressed else 'NO'}")
    if state.business_activity:
        print(f"- Actividad negocio    : {state.business_activity}")
    if state.requirements:
        print(f"- Requisitos web       : {state.requirements}")
    print(f"- Handoff a Hugo pedido: {'SÍ' if state.human_handoff_requested else 'NO'}")
    print(f"- Precio informado     : {'SÍ' if state.pricing_provided else 'NO'}")
    print(f"- Do Not Contact (DNC) : {'ACTIVADO' if state.do_not_contact else 'NO'}")
    print("=" * 75)

    return 0


def main() -> None:
    try:
        code = asyncio.run(async_main())
        sys.exit(code)
    except KeyboardInterrupt:
        print("\nSesión terminada.")
        sys.exit(0)


if __name__ == "__main__":
    main()
