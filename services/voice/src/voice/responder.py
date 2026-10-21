"""Módulo de respuesta comercial determinista mediante reglas y plantillas.

Implementa las respuestas para la Fase 1.3 sin utilizar modelos LLM,
respetando estrictamente las directrices de seguridad de AGENTS.md:
- No inventar precios, disponibilidad de agenda ni compromisos comerciales.
- Identificarse como asistente virtual (nunca presentarse como humano).
- Tratar una solicitud de reunión como una petición pendiente de confirmación.
- Solicitar aclaración cuando la información sea incompleta o ininteligible.
"""

import re
from dataclasses import dataclass
from enum import Enum


class CommercialIntent(str, Enum):
    SERVICE_INFO = "service_info"
    EXPRESS_INTEREST = "express_interest"
    MEETING_REQUEST = "meeting_request"
    UNINTELLIGIBLE = "unintelligible"
    FALLBACK_CLARIFICATION = "fallback_clarification"


@dataclass(frozen=True)
class CommercialResponse:
    intent: CommercialIntent
    response_text: str
    confidence: float
    matched_patterns: list[str]


# Reglas deterministas ordenadas por prioridad de evaluación
_PATTERNS_SERVICE_INFO: list[str] = [
    r"\bqu[eé]\s+(servicios?|hac[eé]is|ofrec[eé]is|ten[eé]is|hacen)\b",
    r"\bcu[aá]l\s+es\s+vuestro\s+(servicio|producto|negocio)\b",
    r"\binformaci[oó]n\s+(sobre|de)\s+(vuestros?|los)\s+servicios?\b",
    r"\bde\s+qu[eé]\s+se\s+trata\b",
    r"\bc[oó]mo\s+funciona\b",
    r"\ba\s+qu[eé]\s+os\s+dedic[aá]is\b",
]

_PATTERNS_EXPRESS_INTEREST: list[str] = [
    r"\bme\s+interesa\b",
    r"\b(envi[aá]r?|mand[aá]r?)\s+(m[aá]s\s+)?informaci[oó]n\b",
    r"\b(envi[aá]r?|mand[aá]r?)\s+un\s+(correo|email|dossier|cat[aá]logo)\b",
    r"\bquiero\s+m[aá]s\s+(detalles|informaci[oó]n)\b",
    r"\bestoy\s+interesado\b",
    r"\bsuena\s+bien\b",
]

_PATTERNS_MEETING_REQUEST: list[str] = [
    r"\b(reuni[oó]n|reunirnos|quedar|vernos)\b",
    r"\bagendar\b",
    r"\b(llamada|videollamada|conferencia)\b",
    r"\b(hacer|tener)\s+una\s+(demo|demostraci[oó]n|cita)\b",
    r"\bcalendario\b",
    r"\bcu[aá]ndo\s+podemos\s+hablar\b",
]

_NOISE_TOKENS = {
    "[música]",
    "[musica]",
    "[ruido]",
    "[silencio]",
    "[inaudible]",
    "[applause]",
    "...",
    ".",
    "",
}


def _clean_text(raw_text: str) -> str:
    if not raw_text:
        return ""
    cleaned = raw_text.strip().lower()
    cleaned = re.sub(r"[¿?¡!.,;:\"'()\[\]]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _matches_any(cleaned_text: str, patterns: list[str]) -> list[str]:
    matches: list[str] = []
    for pattern in patterns:
        if re.search(pattern, cleaned_text, re.IGNORECASE):
            matches.append(pattern)
    return matches


def generate_commercial_response(transcribed_text: str) -> CommercialResponse:
    """Evalúa el texto transcrito y produce una respuesta comercial predecible."""
    if not transcribed_text or not transcribed_text.strip():
        return CommercialResponse(
            intent=CommercialIntent.UNINTELLIGIBLE,
            response_text="Disculpe, no he podido escucharle con claridad. ¿Podría repetir lo que me decía, por favor?",
            confidence=1.0,
            matched_patterns=["empty_input"],
        )

    raw_lower = transcribed_text.strip().lower()
    if raw_lower in _NOISE_TOKENS or len(raw_lower) < 3:
        return CommercialResponse(
            intent=CommercialIntent.UNINTELLIGIBLE,
            response_text="Disculpe, no he recibido un mensaje claro. ¿Podría indicarme en qué puedo orientarle?",
            confidence=0.9,
            matched_patterns=["noise_or_too_short"],
        )

    cleaned = _clean_text(transcribed_text)

    # 1. Petición de reunión (prioridad comercial alta)
    meeting_matches = _matches_any(cleaned, _PATTERNS_MEETING_REQUEST)
    if meeting_matches:
        return CommercialResponse(
            intent=CommercialIntent.MEETING_REQUEST,
            response_text=(
                "Con mucho gusto. Tomo nota de su solicitud de reunión. "
                "¿Qué día y franja horaria le vendría mejor, por la mañana o por la tarde? "
                "Nuestro equipo revisará la agenda y le confirmará la cita por correo."
            ),
            confidence=0.95,
            matched_patterns=meeting_matches,
        )

    # 2. Expresión de interés / solicitud de envío de información
    interest_matches = _matches_any(cleaned, _PATTERNS_EXPRESS_INTEREST)
    if interest_matches:
        return CommercialResponse(
            intent=CommercialIntent.EXPRESS_INTEREST,
            response_text=(
                "Estupendo. Podemos prepararle un resumen con la información técnica y casos de uso. "
                "¿Podría facilitarme su dirección de correo electrónico para que el equipo comercial se lo envíe?"
            ),
            confidence=0.90,
            matched_patterns=interest_matches,
        )

    # 3. Solicitud de información sobre servicios
    service_matches = _matches_any(cleaned, _PATTERNS_SERVICE_INFO)
    if service_matches:
        return CommercialResponse(
            intent=CommercialIntent.SERVICE_INFO,
            response_text=(
                "Hola, soy el asistente virtual de la empresa. "
                "Desarrollamos soluciones de software para automatizar procesos comerciales y de atención al cliente. "
                "Para orientarle mejor, ¿qué tipo de proceso le gustaría optimizar en su negocio?"
            ),
            confidence=0.90,
            matched_patterns=service_matches,
        )

    # 4. Fallback con petición de aclaración respetando no inventar datos
    return CommercialResponse(
        intent=CommercialIntent.FALLBACK_CLARIFICATION,
        response_text=(
            "Gracias por su mensaje. Para poder orientarle adecuadamente, "
            "¿le gustaría conocer nuestros servicios, recibir documentación o coordinar una llamada con nuestro equipo?"
        ),
        confidence=0.50,
        matched_patterns=["fallback_default"],
    )
