"""Prototipo de conversación de voz en tiempo real con Gemini Multimodal Live API.

Este módulo implementa la interacción bidireccional speech-to-speech nativa usando
el SDK oficial `google-genai` y WebSockets, manteniendo el control determinista sobre
las salvaguardas comerciales (precios, DNC, transferencia de llamada) mediante Function Calling.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

# Intentar importar google-genai de forma condicional para permitir tests unitarios con mocks
# incluso si la dependencia externa aún no ha sido sincronizada en el entorno.
try:
    from google import genai
    from google.genai import types

    GENAI_AVAILABLE = True
except ImportError:
    genai = None  # type: ignore
    types = None  # type: ignore
    GENAI_AVAILABLE = False

try:
    import sounddevice as sd

    SOUNDDEVICE_AVAILABLE = True
except (ImportError, OSError):
    sd = None  # type: ignore
    SOUNDDEVICE_AVAILABLE = False

logger = logging.getLogger("voice.gemini_live")


# ============================================================================ #
# Excepciones Específicas                                                      #
# ============================================================================ #


class GeminiLiveError(Exception):
    """Excepción base para incidencias con la sesión de Gemini Live."""


class GeminiLiveConfigError(GeminiLiveError):
    """Configuración ausente o inválida (ej. clave de API faltante)."""


class GeminiLiveQuotaError(GeminiLiveError):
    """Límites de cuota o tasa de solicitudes excedidos (HTTP 429 / RESOURCE_EXHAUSTED)."""


class GeminiLiveConnectionError(GeminiLiveError):
    """Fallo de conexión o interrupción del canal WebSocket."""


class GeminiLiveAudioError(GeminiLiveError):
    """Error al inicializar o transmitir audio hacia/desde el hardware."""


# ============================================================================ #
# Configuración y Estado Comercial                                            #
# ============================================================================ #

DEFAULT_LIVE_MODEL = "gemini-3.8-live"
DEFAULT_LIVE_VOICE = "Puck"
FREE_TIER_PRIVACY_WARNING = (
    "⚠️ AVISO DE PRIVACIDAD (NIVEL GRATUITO):\n"
    "En el nivel gratuito de Google AI Studio, los datos de audio pueden ser procesados\n"
    "y revisados para mejorar los modelos y servicios de Google.\n"
    "No utilices datos personales, reales ni confidenciales durante estas pruebas."
)


@dataclass
class GeminiLiveConfig:
    """Configuración para la sesión en tiempo real de Gemini Live API."""

    api_key: str = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", "").strip()
    )
    model: str = field(
        default_factory=lambda: os.getenv("GEMINI_LIVE_MODEL", DEFAULT_LIVE_MODEL).strip()
    )
    voice_name: str = field(
        default_factory=lambda: os.getenv("GEMINI_LIVE_VOICE", DEFAULT_LIVE_VOICE).strip()
    )
    sample_rate_in: int = 16000  # Formato obligatorio de entrada de Gemini: PCM 16kHz
    sample_rate_out: int = 24000  # Formato estándar de salida de Gemini: PCM 24kHz
    channels: int = 1  # Audio mono
    chunk_size_samples: int = 1600  # 100 ms a 16kHz (3200 bytes PCM 16-bit)
    input_device: int | None = None
    output_device: int | None = None
    agent_name: str = "Hugo"
    base_price_eur: float = 99.0
    max_session_duration_s: float = 900.0  # Límite de sesión de audio continuo (~15 min)

    def validate(self) -> None:
        """Valida que los parámetros indispensables estén presentes."""
        if not self.api_key:
            raise GeminiLiveConfigError(
                "No se ha encontrado la clave de API de Gemini. "
                "Configura la variable de entorno GEMINI_API_KEY antes de iniciar."
            )
        if not self.model:
            raise GeminiLiveConfigError("El identificador del modelo no puede estar vacío.")


@dataclass
class LiveCommercialState:
    """Estado determinista de la conversación comercial administrado por Python."""

    is_decision_maker: bool = False
    has_website: bool | None = None
    business_activity: str | None = None
    interest_expressed: bool = False
    requirements: str | None = None
    human_handoff_requested: bool = False
    handoff_contact: str | None = None
    handoff_notes: str | None = None
    do_not_contact: bool = False
    dnc_reason: str | None = None
    pricing_provided: bool = False
    is_rejected: bool = False
    is_finished: bool = False
    total_turns: int = 0


@dataclass
class LiveSessionMetrics:
    """Métricas y telemetría de la sesión conversacional en vivo."""

    start_time: float = 0.0
    end_time: float = 0.0
    turns_completed: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    interruption_count: int = 0
    tools_invoked: list[str] = field(default_factory=list)
    end_reason: str = "initialized"

    @property
    def duration_s(self) -> float:
        if self.start_time <= 0.0:
            return 0.0
        finish = self.end_time if self.end_time > 0.0 else time.perf_counter()
        return max(0.0, finish - self.start_time)


# ============================================================================ #
# Prompt del Sistema y Reglas Comerciales                                      #
# ============================================================================ #


def build_system_instruction(config: GeminiLiveConfig) -> str:
    """Construye las instrucciones de sistema en español de España con salvaguardas estrictas."""
    return f"""Eres el asistente virtual de {config.agent_name}. Tu misión es ayudar a {config.agent_name} a contactar con pequeños comercios y negocios locales para ofrecerles la creación de su página web profesional.

PERSONALIDAD Y VOZ:
- Hablas en español peninsular (España), con tono cercano, amable, informal y natural.
- Tratas SIEMPRE de «tú», jamás uses «usted».
- Empleas frases cortas y dinámicas, fáciles de comprender por audio (máximo 1 o 2 oraciones por turno).
- Eres directo y conciso. No sueltes discursos largos ni aburridos.
- Haz SOLO UNA pregunta a la vez y espera a escuchar la respuesta completa.
- No repitas tu presentación si ya te has presentado.
- Distingue claramente entre un saludo, una despedida, una respuesta afirmativa y una duda.

REGLAS DE IDENTIDAD Y SEGURIDAD OBLIGATORIAS:
1. IDENTIDAD TRANSPARENTE: Preséntate con honestidad como «el asistente virtual de {config.agent_name}». NUNCA finjas ser humano ni finjas ser {config.agent_name} en persona.
2. PRECIO VERIFICADO: Si preguntan por el precio, explica con claridad que el servicio parte de una tarifa base de {int(config.base_price_eur)} € para una página web completa para el negocio (secciones principales, adaptada a móvil y con botón de contacto o WhatsApp). Aclara que no hay cuotas raras ni precios inventados, y que cualquier funcionalidad a medida se presupuesta aparte. NO inventes cifras, dólares ni descuentos no configurados. Invoca la función get_pricing_and_offer_details.
3. TRANSFERENCIA A HUGO: Si la persona solicita hablar con {config.agent_name} o con una persona humana («pásame con {config.agent_name}», «quiero hablar con alguien real»), debes invocar INMEDIATAMENTE la herramienta request_human_handoff. Explica con total sinceridad que como asistente virtual en pruebas no dispones de transferencia directa de llamada telefónica, pero que le dejas el recado a {config.agent_name} para que le llame o escriba directamente. JAMÁS afirmes que la llamada ha sido transferida.
4. NO CONTACTO (DNC): Si la persona solicita explícitamente no ser contactada («no me llaméis más», «borrad mi número», «dadme de baja»), invoca INMEDIATAMENTE la herramienta request_do_not_contact. Confirma amablemente que queda registrado, pide disculpas por la molestia, despídete con educación y termina la conversación sin insistir bajo ningún concepto.
5. RECHAZO COMERCIAL: Si la persona dice que no le interesa («no me interesa», «no gracias», «ya tenemos web y estamos contentos»), sé comprensivo y educado, da las gracias por el tiempo y despídete sin insistir ni presionar.

FLUJO CONVERSACIONAL DE REFERENCIA:
Paso 1: Saludar con energía y preguntar si hablas con el responsable o encargado del negocio.
Paso 2: Si confirma, explicar en una frase breve que {config.agent_name} diseña webs para ayudar a negocios de la zona a conseguir clientes, y preguntar si ya tienen página web propia.
Paso 3: Si no tienen web, resumir el valor (estar en Google, móvil, contacto fácil) y ver si les gustaría tener una.
Paso 4: Si muestran interés, preguntar a qué se dedican exactamente e invocar record_commercial_interest.
Paso 5: Responder dudas de precio con los {int(config.base_price_eur)} € oficiales y acordar que {config.agent_name} les envíe una propuesta sencilla.
"""


# ============================================================================ #
# Herramientas Deterministas (Function Calling)                                #
# ============================================================================ #


def create_live_tools(
    state: LiveCommercialState,
    config: GeminiLiveConfig,
    metrics: LiveSessionMetrics | None = None,
) -> list[Callable[..., Any]]:
    """Crea la lista de herramientas Python para que el modelo invoque acciones deterministas."""

    def record_commercial_interest(business_activity: str, requirements: str = "") -> dict[str, Any]:
        """Registra el interés comercial del cliente, la actividad de su negocio y sus requisitos.

        Args:
            business_activity: Sector o actividad del negocio del cliente (ej. fontanería, restaurante).
            requirements: Qué necesita en su web (ej. carta online, reservas, tienda, contacto).
        """
        state.interest_expressed = True
        state.business_activity = business_activity.strip()
        state.requirements = requirements.strip() if requirements else None
        if metrics is not None:
            metrics.tools_invoked.append("record_commercial_interest")
        logger.info(
            "Acción comercial: Interés registrado | Actividad: %s | Requisitos: %s",
            business_activity,
            requirements,
        )
        return {
            "status": "success",
            "message": f"Interés registrado correctamente para negocio de {business_activity}.",
            "action_taken": "recorded_interest",
        }

    def request_human_handoff(contact_name: str = "", notes: str = "") -> dict[str, Any]:
        """Registra la solicitud del cliente de hablar directamente con Hugo o un humano.

        Args:
            contact_name: Nombre de la persona de contacto si lo ha facilitado.
            notes: Notas adicionales o motivo de la consulta.
        """
        state.human_handoff_requested = True
        state.handoff_contact = contact_name.strip() if contact_name else None
        state.handoff_notes = notes.strip() if notes else None
        if metrics is not None:
            metrics.tools_invoked.append("request_human_handoff")
        logger.info(
            "Acción comercial: Handoff a humano solicitado | Contacto: %s | Notas: %s",
            contact_name,
            notes,
        )
        return {
            "status": "registered",
            "message": f"Solicitud registrada para {config.agent_name}. No hay transferencia telefónica activa.",
            "has_real_transfer": False,
            "agent_contact_name": config.agent_name,
        }

    def request_do_not_contact(reason: str = "") -> dict[str, Any]:
        """Registra la petición expresa del usuario de no volver a ser contactado (Lista Robinson/DNC).

        Args:
            reason: Motivo expresado por el usuario para la exclusión.
        """
        state.do_not_contact = True
        state.dnc_reason = reason.strip() if reason else "solicitud_usuario"
        state.is_finished = True
        if metrics is not None:
            metrics.tools_invoked.append("request_do_not_contact")
        logger.info("Acción comercial: DNC activado | Motivo: %s", reason)
        return {
            "status": "dnc_confirmed",
            "message": "Número y contacto marcados para no volver a llamar. Conversación terminada.",
            "must_stop_immediately": True,
        }

    def get_pricing_and_offer_details() -> dict[str, Any]:
        """Consulta la información oficial, transparente y verificada sobre precios y servicios de diseño web."""
        state.pricing_provided = True
        if metrics is not None:
            metrics.tools_invoked.append("get_pricing_and_offer_details")
        return {
            "base_price_eur": config.base_price_eur,
            "currency": "EUR",
            "includes": [
                "Diseño web profesional adaptado a móviles y tablets",
                "Secciones informativas de servicios y presentación del negocio",
                "Integración con WhatsApp y formulario de contacto directo",
                "Optimización básica para búsqueda local en Google",
            ],
            "custom_features_notice": "Cualquier desarrollo avanzado (tiendas online complejas, reservas automáticas) se presupuesta a medida sin compromiso.",
        }

    return [
        record_commercial_interest,
        request_human_handoff,
        request_do_not_contact,
        get_pricing_and_offer_details,
    ]


def list_available_models(api_key: str) -> list[str]:
    """Consulta la API de Google GenAI y devuelve los nombres de modelos disponibles para la clave."""
    if not GENAI_AVAILABLE or genai is None:
        raise GeminiLiveConfigError(
            "El paquete oficial 'google-genai' no está instalado en el entorno. "
            "Ejecuta 'uv add google-genai' para instalarlo."
        )
    if not api_key:
        raise GeminiLiveConfigError("No se ha proporcionado una clave GEMINI_API_KEY.")

    client = genai.Client(api_key=api_key)
    try:
        models = client.models.list()
        return [getattr(m, "name", str(m)) for m in models]
    except Exception as exc:
        err_msg = str(exc)
        if "403" in err_msg or "PERMISSION_DENIED" in err_msg or "API_KEY_INVALID" in err_msg:
            raise GeminiLiveConfigError(f"Error de autenticación: clave de API inválida: {exc}") from exc
        raise GeminiLiveConnectionError(f"Error al consultar la lista de modelos: {exc}") from exc


# ============================================================================ #
# Sesión Conversacional en Tiempo Real (Gemini Live API)                        #
# ============================================================================ #


class GeminiLiveSession:
    """Gestiona la conexión WebSocket bidireccional de audio con Gemini Live API."""

    def __init__(
        self,
        config: GeminiLiveConfig | None = None,
        state: LiveCommercialState | None = None,
    ) -> None:
        self.config = config or GeminiLiveConfig()
        self.config.validate()
        self.state = state or LiveCommercialState()
        self.metrics = LiveSessionMetrics()
        self._stop_event = asyncio.Event()
        self._audio_out_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._playback_stream: Any = None
        self._capture_stream: Any = None

    def _create_genai_client(self) -> Any:
        """Crea e inicializa el cliente oficial de GenAI."""
        if not GENAI_AVAILABLE or genai is None:
            raise GeminiLiveConfigError(
                "El paquete oficial 'google-genai' no está instalado en el entorno. "
                "Ejecuta 'uv add google-genai' para instalarlo."
            )
        return genai.Client(api_key=self.config.api_key)

    def _build_connect_config(self, tools: list[Callable[..., Any]]) -> Any:
        """Crea la configuración de conexión tipada para el Live API."""
        if not GENAI_AVAILABLE or types is None:
            raise GeminiLiveConfigError("El SDK 'google-genai' no está disponible.")

        # Configuramos respuesta de audio nativa y voz seleccionada
        # Usamos ['AUDIO'] como lista de strings conforme a la documentación oficial del SDK
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.config.voice_name
                    )
                )
            ),
            system_instruction=build_system_instruction(self.config),
            tools=tools,
        )

    async def _audio_capture_task(
        self,
        session: Any,
        input_queue: asyncio.Queue[bytes],
    ) -> None:
        """Lee bloques de PCM de la cola del micrófono y los envía a Gemini."""
        try:
            while not self._stop_event.is_set():
                try:
                    chunk = await asyncio.wait_for(input_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue

                if chunk:
                    self.metrics.bytes_sent += len(chunk)
                    mime_type = f"audio/pcm;rate={self.config.sample_rate_in}"
                    audio_blob = (
                        types.Blob(data=chunk, mime_type=mime_type)
                        if types is not None
                        else chunk
                    )
                    if hasattr(session, "send_realtime_input"):
                        await session.send_realtime_input(audio=audio_blob)
                    elif hasattr(session, "send"):
                        await session.send(input=audio_blob)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("Error en tarea de captura de audio: %s", exc)

    async def _audio_playback_task(self) -> None:
        """Consume bloques de audio recibidos de Gemini y los escribe en el altavoz."""
        try:
            while not self._stop_event.is_set():
                try:
                    chunk = await asyncio.wait_for(self._audio_out_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue

                if chunk is None:
                    break

                if self._playback_stream is not None:
                    try:
                        self._playback_stream.write(chunk)
                    except Exception as exc:
                        logger.warning("Error escribiendo en stream de altavoz: %s", exc)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("Error en tarea de reproducción de audio: %s", exc)

    def _clear_playback_queue(self) -> None:
        """Vacía la cola de reproducción inmediatamente ante una interrupción (barge-in)."""
        cleared_chunks = 0
        while not self._audio_out_queue.empty():
            try:
                self._audio_out_queue.get_nowait()
                cleared_chunks += 1
            except asyncio.QueueEmpty:
                break
        if cleared_chunks > 0:
            logger.debug("Barge-in: Se descartaron %d bloques de audio en cola.", cleared_chunks)

    async def _handle_server_response(
        self,
        response: Any,
        session: Any,
        tool_map: dict[str, Callable[..., Any]],
    ) -> None:
        """Procesa una respuesta del servidor: audio, interrupción o llamada a herramientas."""
        # 1. Verificar eventos del servidor
        server_content = getattr(response, "server_content", None)
        if server_content is not None:
            # Detección de interrupción (el usuario empezó a hablar mientras el modelo respondía)
            if getattr(server_content, "interrupted", False):
                self.metrics.interruption_count += 1
                logger.info("⚡ Interrupción detectada (barge-in). Cortando habla del modelo.")
                self._clear_playback_queue()

            # Extracción de audio del turno del modelo
            model_turn = getattr(server_content, "model_turn", None)
            if model_turn is not None:
                parts = getattr(model_turn, "parts", [])
                for part in parts:
                    inline_data = getattr(part, "inline_data", None)
                    if inline_data is not None and getattr(inline_data, "data", None):
                        data_bytes = inline_data.data
                        self.metrics.bytes_received += len(data_bytes)
                        await self._audio_out_queue.put(data_bytes)

                    # Verificar si viene una llamada a función dentro de una parte
                    function_call = getattr(part, "function_call", None)
                    if function_call is not None:
                        await self._execute_and_reply_tool(function_call, session, tool_map)

            if getattr(server_content, "turn_complete", False):
                self.metrics.turns_completed += 1
                self.state.total_turns += 1
                logger.debug("Turno del modelo completado. Turnos totales: %d", self.metrics.turns_completed)

        # 2. Verificar llamada a herramienta a nivel superior de respuesta
        tool_call = getattr(response, "tool_call", None)
        if tool_call is not None:
            function_calls = getattr(tool_call, "function_calls", [])
            for fc in function_calls:
                await self._execute_and_reply_tool(fc, session, tool_map)

    async def _execute_and_reply_tool(
        self,
        fc: Any,
        session: Any,
        tool_map: dict[str, Callable[..., Any]],
    ) -> None:
        """Ejecuta deterministamente una herramienta y envía el resultado de vuelta a Gemini."""
        func_name = getattr(fc, "name", "")
        call_id = getattr(fc, "id", None)
        raw_args = getattr(fc, "args", {}) or {}
        func_args = dict(raw_args) if isinstance(raw_args, dict) else {}

        logger.info("🔧 Invocación de herramienta solicitada por Gemini: %s(args=%s)", func_name, func_args)

        func = tool_map.get(func_name)
        if func is not None:
            try:
                result = func(**func_args)
            except Exception as e:
                logger.error("Error ejecutando herramienta '%s': %s", func_name, e)
                result = {"status": "error", "message": str(e)}
        else:
            logger.warning("Herramienta desconocida solicitada: %s", func_name)
            result = {"status": "error", "message": f"Herramienta '{func_name}' no soportada."}

        # Enviar respuesta estructurada de vuelta a la sesión Live
        try:
            if types is not None:
                func_response = types.FunctionResponse(
                    name=func_name,
                    id=call_id,
                    response={"result": result},
                )
            else:
                func_response = {
                    "name": func_name,
                    "id": call_id,
                    "response": {"result": result},
                }

            if hasattr(session, "send_tool_response"):
                await session.send_tool_response(function_responses=func_response)
            elif hasattr(session, "send"):
                tool_resp = (
                    types.LiveClientToolResponse(function_responses=[func_response])
                    if types is not None
                    else {"function_responses": [func_response]}
                )
                await session.send(tool_response=tool_resp)
        except Exception as exc:
            logger.error("Error enviando respuesta de herramienta a Gemini: %s", exc)

        # Si se activó DNC o fin de conversación, solicitar parada suave
        if self.state.do_not_contact or self.state.is_finished:
            logger.info("Conversación finalizada deterministamente por regla comercial.")

    async def run(self) -> LiveSessionMetrics:
        """Ejecuta el ciclo de vida completo de la sesión conversacional en vivo."""
        client = self._create_genai_client()
        tools = create_live_tools(self.state, self.config, self.metrics)
        tool_map = {tool.__name__: tool for tool in tools}
        connect_config = self._build_connect_config(tools)

        self.metrics.start_time = time.perf_counter()
        logger.info("Iniciando sesión con modelo %s y voz %s", self.config.model, self.config.voice_name)

        input_queue: asyncio.Queue[bytes] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        # Configurar callback para sounddevice InputStream
        def mic_callback(indata: Any, frames: int, time_info: Any, status: Any) -> None:
            if status:
                logger.warning("Alerta de hardware en micrófono: %s", status)
            # indata es un buffer continuo de int16
            raw_bytes = bytes(indata)
            loop.call_soon_threadsafe(input_queue.put_nowait, raw_bytes)

        # Inicializar dispositivos si sounddevice está disponible
        use_audio_hardware = SOUNDDEVICE_AVAILABLE and sd is not None
        if use_audio_hardware:
            try:
                self._capture_stream = sd.RawInputStream(
                    samplerate=self.config.sample_rate_in,
                    channels=self.config.channels,
                    dtype="int16",
                    blocksize=self.config.chunk_size_samples,
                    device=self.config.input_device,
                    callback=mic_callback,
                )
                self._playback_stream = sd.RawOutputStream(
                    samplerate=self.config.sample_rate_out,
                    channels=self.config.channels,
                    dtype="int16",
                    device=self.config.output_device,
                )
                self._capture_stream.start()
                self._playback_stream.start()
                logger.info("Dispositivos de audio en tiempo real iniciados correctamente.")
            except Exception as err:
                logger.warning("No se pudo iniciar el hardware de audio real: %s", err)
                use_audio_hardware = False

        capture_task: asyncio.Task[None] | None = None
        playback_task: asyncio.Task[None] | None = None

        try:
            async with client.aio.live.connect(model=self.config.model, config=connect_config) as session:
                logger.info("✅ Conexión establecida con Gemini Live API.")

                capture_task = asyncio.create_task(self._audio_capture_task(session, input_queue))
                playback_task = asyncio.create_task(self._audio_playback_task())

                async for response in session.receive():
                    if self._stop_event.is_set():
                        break

                    await self._handle_server_response(response, session, tool_map)

                    # Verificar si la sesión debe terminar
                    if self.state.do_not_contact:
                        # Dar un breve instante para que termine de reproducir la despedida
                        await asyncio.sleep(2.5)
                        self.metrics.end_reason = "do_not_contact"
                        break

                    # Comprobar límite de duración de sesión de nivel gratuito
                    if self.metrics.duration_s >= self.config.max_session_duration_s:
                        logger.warning("Límite de tiempo de sesión alcanzado (%0.1f s).", self.config.max_session_duration_s)
                        self.metrics.end_reason = "max_duration_reached"
                        break

                if self.metrics.end_reason == "initialized":
                    self.metrics.end_reason = "completed_normally"

        except asyncio.CancelledError:
            self.metrics.end_reason = "cancelled_by_user"
            logger.info("Sesión cancelada por el usuario (Ctrl+C).")
        except Exception as exc:
            err_str = str(exc)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                self.metrics.end_reason = "quota_exceeded"
                logger.error("❌ Límite de cuota alcanzado en Gemini Live API: %s", exc)
                raise GeminiLiveQuotaError(
                    "Se ha alcanzado el límite de cuota o solicitudes concurrentes en el nivel gratuito. "
                    "Espera unos minutos antes de volver a intentarlo."
                ) from exc
            self.metrics.end_reason = f"error: {exc}"
            logger.error("Error durante la sesión de Gemini Live: %s", exc)
            raise GeminiLiveConnectionError(f"Error en sesión Live: {exc}") from exc
        finally:
            self._stop_event.set()
            self.metrics.end_time = time.perf_counter()

            if capture_task is not None and not capture_task.done():
                capture_task.cancel()
            if playback_task is not None and not playback_task.done():
                playback_task.cancel()

            # Detener y cerrar streams de sounddevice
            if self._capture_stream is not None:
                try:
                    self._capture_stream.stop()
                    self._capture_stream.close()
                except Exception:
                    pass
                self._capture_stream = None

            if self._playback_stream is not None:
                try:
                    self._playback_stream.stop()
                    self._playback_stream.close()
                except Exception:
                    pass
                self._playback_stream = None

            logger.info(
                "Sesión Live finalizada | Causa: %s | Duración: %.1fs | Turnos: %d",
                self.metrics.end_reason,
                self.metrics.duration_s,
                self.metrics.turns_completed,
            )

        return self.metrics
