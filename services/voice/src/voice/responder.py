"""Módulo de respuesta comercial determinista para el asistente virtual de Hugo (Fase 3).

Especializado en la venta cercana y natural de páginas web a pequeños negocios locales,
cumpliendo estrictamente con AGENTS.md:
- No inventar precios cerrados universales ni disponibilidad de agenda.
- Identificarse siempre como asistente virtual de Hugo (nunca presentarse como humano ni afirmar ser Hugo).
- Tratar cualquier solicitud de reunión como una propuesta pendiente de confirmación.
- Gestión prioritaria e irreversible del estado de exclusión y bajas (DO_NOT_CONTACT).
- Distinguir entre rechazo suave (soft_rejection), despedida (farewell) y solicitud expresa de baja (do_not_contact).
- Soporte para conversaciones multi-turno con gestión de estado sin base de datos pesada.
- Estilo coloquial peninsular ("tú", natural, frases cortas, sin formalismos de centralita).
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CommercialIntent(str, Enum):
    # 1. Saludo y apertura
    GREETING_PRESENTATION = "greeting_presentation"
    # 2. Información del servicio de webs
    SERVICE_INFO = "service_info"
    # 3. Expresión de interés / solicitud de propuesta
    EXPRESS_INTEREST = "express_interest"
    # 4. Solicitud de reunión / llamada
    MEETING_REQUEST = "meeting_request"
    # 5. Pregunta de precio / objeción presupuestaria
    PRICE_INQUIRY = "price_inquiry"
    # 6. Falta de tiempo / ocupado
    BUSY_CALL_LATER = "busy_call_later"
    # 7. Competidor existente / ya tiene proveedor
    EXISTING_COMPETITOR = "existing_competitor"
    # 8. Rechazo comercial sin baja explícita
    SOFT_REJECTION = "soft_rejection"
    # 9. Solicitud expresa de no contacto / baja (DNC)
    DO_NOT_CONTACT = "do_not_contact"
    # 10. Petición de rellamada en horario propuesto
    CALLBACK_REQUEST = "callback_request"
    # 11. Petición de transferencia a Hugo o persona real
    HUMAN_HANDOFF_REQUESTED = "human_handoff_requested"
    TRANSFER_HUMAN = HUMAN_HANDOFF_REQUESTED
    # 12. Dudas de privacidad y RGPD
    PRIVACY_INQUIRY = "privacy_inquiry"
    # 13. Integraciones técnicas / APIs
    TECHNICAL_INTEGRATION = "technical_integration"
    # 14. Disponibilidad de agenda
    SCHEDULE_AVAILABILITY = "schedule_availability"
    # 15. Información desconocida / fuera de alcance
    UNKNOWN_INFO = "unknown_info"
    # 16. Retirada de interés previa / arrepentimiento
    INTEREST_WITHDRAWAL = "interest_withdrawal"
    # 17. Ininteligible / silencio / ruido
    UNINTELLIGIBLE = "unintelligible"
    # 18. Fallback / ambiguo / fuera de dominio
    FALLBACK_CLARIFICATION = "fallback_clarification"
    # 19. Despedida explícita
    FAREWELL = "farewell"
    # 20. Confirmación de decisor
    DECISION_MAKER_CONFIRMATION = "decision_maker_confirmation"
    # 21. Cualificación: no tiene web
    HAS_NO_WEBSITE = "has_no_website"
    # 22. Cualificación: ya tiene web
    HAS_WEBSITE = "has_website"
    # 23. Respuesta afirmativa contextual ("sí, cuéntame")
    AFFIRMATIVE_CONTINUE = "affirmative_continue"


class CommercialStage(str, Enum):
    """Etapas del funnel comercial de venta de webs de Hugo."""
    OPENING = "opening"
    IDENTIFY_DECISION_MAKER = "identify_decision_maker"
    QUALIFY_WEBSITE = "qualify_website"
    EXPLAIN_OFFER = "explain_offer"
    QUALIFY_INTEREST = "qualify_interest"
    COLLECT_REQUIREMENTS = "collect_requirements"
    HUMAN_HANDOFF_REQUESTED = "human_handoff_requested"
    OBJECTION_HANDLING = "objection_handling"
    CLOSING = "closing"
    REJECTED = "rejected"
    DO_NOT_CONTACT = "do_not_contact"
    FINISHED = "finished"


@dataclass
class CommercialConfig:
    """Configuración centralizada y editable de la propuesta comercial de Hugo."""
    agent_name: str = "Hugo"
    service_type: str = "diseño y desarrollo de páginas web para pequeños negocios locales"
    starting_price: float = 99.0
    price_currency: str = "€"
    included_features: tuple[str, ...] = (
        "web adaptada a móviles",
        "sección de servicios y fotos del negocio",
        "ubicación y horarios",
        "botón directo de contacto por WhatsApp",
    )
    extra_conditions: tuple[str, ...] = (
        "El precio orientativo de 99 € cubre una web básica de una página",
        "Funcionalidades como tienda online, pasarelas de pago o reservas complejas requieren presupuesto personalizado por parte de Hugo",
    )
    delivery_time_days_min: int = 5
    delivery_time_days_max: int = 10
    has_telephony_transfer: bool = False
    contact_email: str = "hugo@ejemplo.com"
    allowed_contact_hours: str = "de lunes a viernes de 9:00 a 19:00"


DEFAULT_COMMERCIAL_CONFIG = CommercialConfig()


@dataclass
class ConversationContext:
    """Modelo de estado conversacional en memoria para evaluación multi-turno."""
    history: list[tuple[str, str]] = field(default_factory=list)
    current_intent: CommercialIntent | None = None
    previous_intent: CommercialIntent | None = None
    stage: CommercialStage = CommercialStage.OPENING
    is_do_not_contact: bool = False
    is_rejected: bool = False
    interest_expressed: bool = False
    meeting_requested: bool = False
    human_handoff_requested: bool = False
    turn_count: int = 0

    # Hugo Sales Script Context Tracking:
    has_presented_self: bool = False
    is_decision_maker: bool | None = None
    has_own_website: bool | None = None
    proposal_requested: bool = False
    is_finished: bool = False
    requirements_gathered: dict[str, Any] = field(default_factory=dict)
    last_question_asked: str | None = None

    def record_turn(self, user_text: str, agent_reply: str, intent: CommercialIntent) -> None:
        self.history.append((user_text, agent_reply))
        self.previous_intent = self.current_intent
        self.current_intent = intent
        self.turn_count += 1

        if intent == CommercialIntent.DO_NOT_CONTACT:
            self.is_do_not_contact = True
            self.is_rejected = True
            self.is_finished = True
            self.stage = CommercialStage.DO_NOT_CONTACT
        elif intent == CommercialIntent.SOFT_REJECTION:
            self.is_rejected = True
            self.is_finished = True
            self.stage = CommercialStage.REJECTED
        elif intent in (CommercialIntent.EXPRESS_INTEREST, CommercialIntent.MEETING_REQUEST):
            self.interest_expressed = True
            if intent == CommercialIntent.MEETING_REQUEST:
                self.meeting_requested = True
        elif intent in (CommercialIntent.TRANSFER_HUMAN, CommercialIntent.HUMAN_HANDOFF_REQUESTED):
            self.human_handoff_requested = True
            self.stage = CommercialStage.HUMAN_HANDOFF_REQUESTED
        elif intent == CommercialIntent.INTEREST_WITHDRAWAL:
            self.interest_expressed = False
            self.meeting_requested = False
            self.proposal_requested = False
            self.is_rejected = True
            self.stage = CommercialStage.REJECTED
        elif intent == CommercialIntent.FAREWELL:
            self.is_finished = True
            self.stage = CommercialStage.FINISHED


@dataclass(frozen=True)
class CommercialResponse:
    """Estructura inmutable de respuesta emitida por el motor de decisión."""
    intent: CommercialIntent
    response_text: str
    confidence: float
    matched_patterns: list[str]
    is_do_not_contact: bool = False
    context: ConversationContext | None = None


# --- CATÁLOGO DE PATRONES DETERMINISTAS ---

_PATTERNS_DO_NOT_CONTACT: list[str] = [
    r"\bno\s+(me\s+|nos\s+)?(volv\w*\s+a\s+(llamar|contact\w*|molest\w*)|llam\w*\s+m[aá]s|contact\w*\s+m[aá]s|molest\w*)\b",
    r"\bno\s+(me\s+|nos\s+)?(llames|llame|llam[eé]is|llamen|contactes|contacte|contacten)\b",
    r"\bborr\w*\s+(mi\s+|mis\s+|nuestro\s+|nuestros\s+)?(n[uú]mero|contacto|datos|tel[eé]fono)\b",
    r"\b(da[rd]\w*|dar)\s+de\s+baja\b",
    r"\bno\s+quiero\s+(que\s+(me\s+|nos\s+)?llam\w*|recib\w*\s+(m[aá]s\s+)?(llamadas|mensajes|comunicaciones)|m[aá]s\s+(llamadas|contacto|mensajes))\b",
    r"\belimin\w*\s+((mi\s+|mis\s+|nuestro\s+|nuestros\s+)?(n[uú]mero|contacto|datos|tel[eé]fono)\s+)?de\s+(la|vuestra)\s+lista\b",
    r"\blista\s+robinson\b",
    r"\bno\s+volv\w*\s+(a\s+)?llamar\b",
]

_PATTERNS_INTEREST_WITHDRAWAL: list[str] = [
    r"\bpens[aá]ndolo\s+bien\s+(ya\s+no|mejor\s+no|lo\s+dejamos)\b",
    r"\bya\s+no\s+(me\s+|nos\s+)?interesa\b",
    r"\bcancel\w*\s+(la\s+)?(cita|reuni[oó]n|solicitud|petici[oó]n|informaci[oó]n|propuesta)\b",
    r"\bolv[ií]da(lo|te)|d[eé]jalo\b",
    r"\bal\s+final\s+(no|nada|lo\s+dejamos)\b",
    r"\bme\s+he\s+arrepentido\b",
]

_PATTERNS_TRANSFER_HUMAN: list[str] = [
    r"\b(hablar\s+con\s+hugo|p[aá]same\s+con\s+hugo|quiero\s+hablar\s+con\s+hugo|prefiero\s+hablar\s+con\s+hugo)\b",
    r"\b(p[aá]s\w*|hablar)\s+(con\s+)?(una\s+persona|un\s+humano|alguien\s+real|un\s+operador|un\s+agente\s+humano)\b",
    r"\bp[aá]s\w*\s+con\s+(tu\s+)?(jefe|responsable|superior|encargado)\b",
    r"\bquiero\s+hablar\s+con\s+(una\s+persona|alguien\s+de\s+verdad|alguien\s+humano)\b",
    r"\beres\s+(un\s+)?robot\b",
]

_PATTERNS_FAREWELL: list[str] = [
    r"\b(adi[oó]s|hasta\s+luego|hasta\s+pronto|chao|chau)\b",
    r"\bmuchas\s+gracias\s+(por\s+todo\s+)?(adi[oó]s|hasta\s+luego)\b",
    r"\bgracias\s+por\s+la\s+informaci[oó]n\b",
    r"\b(eso\s+es\s+todo|ya\s+estar[ií]a|no\s+necesito\s+nada\s+m[aá]s)\b",
    r"\bya\s+est[aá]\s+todo\b",
]

_PATTERNS_DECISION_MAKER_CONFIRMATION: list[str] = [
    r"\b(s[ií]\s+)?(soy\s+yo|con\s+[eé]l\s+hablas|con\s+ella\s+hablas|al\s+aparato|yo\s+lo\s+llevo|yo\s+soy\s+el\s+(dueño|responsable|jefe|encargado))\b",
    r"\bqu[eé]\s+quer[ií]as\b",
]

_PATTERNS_HAS_NO_WEBSITE: list[str] = [
    r"\b(no\s+tenemos|no\s+tengo)\s+(p[aá]gina\s+)?web\b",
    r"\bno\s+(tenemos|tengo)\s+nada\b",
    r"\btodav[ií]a\s+no\b",
]

_PATTERNS_HAS_WEBSITE: list[str] = [
    r"\b(s[ií]\s+)?(ya\s+)?(tenemos|tengo)\s+(p[aá]gina\s+)?web\b",
    r"\bya\s+est[aá]\s+hecha\b",
]

_PATTERNS_AFFIRMATIVE_CONTINUE: list[str] = [
    r"\b(s[ií]\s+)?cu[eé]ntame\b",
    r"\ba\s+ver\s+cu[eé]ntame\b",
    r"\bdime\s+a\s+ver\b",
    r"^(s[ií]|vale|venga|claro|de\s+acuerdo|adelante|dale)$",
]

_PATTERNS_PRIVACY_INQUIRY: list[str] = [
    r"\bde\s+d[oó]nde\s+(hab[eé]is|has|han)\s+sacado\s+(mi\s+)?(n[uú]mero|tel[eé]fono|datos)\b",
    r"\bc[oó]mo\s+ten[eé]is\s+(mi\s+)?(n[uú]mero|tel[eé]fono|contacto)\b",
    r"\bpol[ií]tica\s+de\s+privacidad\b",
    r"\b(protecci[oó]n\s+de\s+datos|rgpd|lopd)\b",
    r"\bqu[eé]\s+hac\w*\b.*\bdatos\b",
]

_PATTERNS_PRICE_INQUIRY: list[str] = [
    r"\bcu[aá]nto\s+(cuesta|vale|cobran|sale)\b",
    r"\bqu[eé]\s+precio\s+tiene\b",
    r"\b(tarifas?|precios?|costes?|costos?)\b",
    r"\bno\s+tenemos\s+presupuesto\b",
    r"\b(es|parece|ser[aá]|resulta|va\s+a\s+ser)\s+(muy\s+)?car[oa]s?\b",
]

_PATTERNS_BUSY_CALL_LATER: list[str] = [
    r"\bahora\s+no\s+puedo\s+hablar\b",
    r"\bestoy\s+(muy\s+)?(ocupado|liado)\b",
    r"\bestoy\s+con\s+un\s+cliente\b",
    r"\bestoy\s+en\s+una\s+reuni[oó]n\b",
    r"\bpill\w*\s+(muy\s+|bastante\s+)?mal\b",
    r"\ben\s+mal\s+momento\b",
    r"\bahora\s+mismo\s+imposible\b",
    r"\bimposible\s+atender\w*\b",
]

_PATTERNS_CALLBACK_REQUEST: list[str] = [
    r"\b(ll[aá]m\w*|habl\w*)\s+(luego|m[aá]s\s+tarde|mañana|el\s+(pr[oó]ximo\s+)?\w+|la\s+semana\s+que\s+viene|por\s+la\s+tarde|en\s+otro\s+momento)\b",
    r"\bpuedes\s+llamar\s+(m[aá]s\s+tarde|luego|mañana)\b",
    r"\bllamadme\s+(a\s+las\s+\d+|en\s+otro\s+momento)\b",
]

_PATTERNS_EXISTING_COMPETITOR: list[str] = [
    r"\bya\s+(trabajamos|tenemos|usamos|utilizamos|contamos)\s+(con\s+)?(otro|otra|un|una|proveedor|servicio|sistema|empresa|software|herramienta|salesforce|hubspot)\b",
    r"\b(estamos\s+contentos\s+con\s+)?nuestro\s+proveedor\b",
    r"\bya\s+lo\s+tenemos\s+cubierto\b",
]

_PATTERNS_SOFT_REJECTION: list[str] = [
    r"\bno\s+(nos\s+|me\s+)?interesa\b",
    r"\bno\s+(nos\s+|me\s+)?encaja\b",
    r"\bno\s+lo\s+vemos\s+viable\b",
    r"\bno\s+lo\s+necesitamos\b",
    r"\bde\s+momento\s+no\b",
    r"\bgracias\s+pero\s+no\b",
    r"\bno\s+gracias\b",
    r"\bno\s+queremos\s+(una\s+)?web\b",
]

_PATTERNS_TECHNICAL_INTEGRATION: list[str] = [
    r"\bse\s+integra\s+con\b",
    r"\bten[eé]is\s+integraci[oó]n\b",
    r"\bconect\w*\s+con\s+(nuestro\s+)?(crm|erp|software|sistema|sap|hubspot|salesforce|woocommerce)\b",
    r"\bdispon[eé]is\s+de\s+apis?\b",
    r"\bten[eé]is\s+apis?\b",
    r"\bwebhooks?\b",
    r"\bes\s+compatible\s+con\b",
]

_PATTERNS_SCHEDULE_AVAILABILITY: list[str] = [
    r"\bqu[eé]\s+d[ií]as\s+ten[eé]is\s+(libres?|disponibles?)\b",
    r"\bten[eé]is\s+hueco\b",
    r"\bcu[aá]ndo\s+ten[eé]is\s+agenda\b",
    r"\bqu[eé]\s+horarios?\s+hay\s+disponibles?\b",
    r"\best[aá]is\s+disponibles?\s+(mañana|hoy|el\s+\w+)\b",
]

_PATTERNS_MEETING_REQUEST: list[str] = [
    r"\b(reuni[oó]n|reunirnos|quedar|vernos)\b",
    r"\bagendar\b",
    r"\b(llamada|videollamada|conferencia)\b",
    r"\b(hacer|tener|ver|pedir)?\s*(una\s+)?(demo|demostraci[oó]n|cita)\b",
    r"\bcu[aá]ndo\s+podemos\s+hablar\b",
]

_PATTERNS_EXPRESS_INTEREST: list[str] = [
    r"\b(ver|mandar|enviar|hacer)\s+(una\s+)?propuesta\b",
    r"\bme\s+interesa\b",
    r"\bestoy\s+interesad[oa]\b",
    r"\b(envi|mand|recib)\w*\s+(un\s+)?(correo|email|dossier|cat[aá]logo|informaci[oó]n|detalles)\b",
    r"\b(envi|mand)\w*\s+(m[aá]s\s+)?(informaci[oó]n|detalles)\b",
    r"\bquiero\s+m[aá]s\s+(detalles|informaci[oó]n)\b",
    r"\bsuena\s+bien\b",
    r"\bparece\s+interesante\b",
]

_PATTERNS_SERVICE_INFO: list[str] = [
    r"\bqu[eé]\s+(tipo\s+de\s+|clase\s+de\s+)?(servicios?|hac[eé]is|ofrec[eé]is|ten[eé]is|hacen)\b",
    r"\bcu[aá]l(es)?\s+(es|son)\s+(vuestros?|los|sus)?\s*(servicios?|productos?|negocios?)\b",
    r"\binformaci[oó]n\s+(sobre|de)\s+(vuestros?|los|sus)?\s*servicios?\b",
    r"\b(saber|conocer)\s+(m[aá]s\s+)?(sobre|de)\s+(vuestros?|los|sus)?\s*servicios?\b",
    r"\b(explic\w*|cont\w*)\s+(vuestros?|los|sus)?\s*servicios?\b",
    r"\bten[eé]is\s+servicios?\b",
    r"\bde\s+qu[eé]\s+se\s+trata\b",
    r"\bc[oó]mo\s+funciona\b",
    r"\ba\s+qu[eé]\s+os\s+dedic[aá]is\b",
]

_PATTERNS_UNKNOWN_INFO: list[str] = [
    r"\bd[oó]nde\s+est[aá]\s+vuestra\s+(sede|oficina)(\s+central)?\s+en\b",
    r"\bcu[aá]nto\s+factur\w*\b",
    r"\bcu[aá]ntos\s+empleados\s+sois\b",
    r"\bqui[eé]n\s+es\s+vuestro\s+(ceo|director|dueño)\b",
]

_PATTERNS_GREETING_PRESENTATION: list[str] = [
    r"\b(hola|buenos\s+d[ií]as|buenas\s+tardes|buenas)\b",
    r"\bqui[eé]n\s+eres\b",
    r"\bcon\s+qui[eé]n\s+hablo\b",
    r"\bde\s+parte\s+de\s+qui[eé]n\b",
    r"\bqui[eé]n\s+(llama|es)\b",
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


def _remove_accents(text: str) -> str:
    """Normaliza vocales con tilde y diéresis para garantizar coincidencias robustas en español peninsular."""
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
    }
    for accented, unaccented in replacements.items():
        text = text.replace(accented, unaccented)
    return text


def _clean_text(raw_text: str) -> str:
    if not raw_text:
        return ""
    cleaned = raw_text.strip().lower()
    cleaned = re.sub(r"[¿?¡!.,;:\"'()\[\]]", " ", cleaned)
    cleaned = _remove_accents(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _matches_any(cleaned_text: str, patterns: list[str]) -> list[str]:
    matches: list[str] = []
    for pattern in patterns:
        if re.search(pattern, cleaned_text, re.IGNORECASE):
            matches.append(pattern)
    return matches


# --- CLASIFICACIÓN DE INTENCIÓN ---

def classify_intent(
    cleaned_text: str,
    context: ConversationContext | None = None,
) -> tuple[CommercialIntent, float, list[str]]:
    """Clasifica el texto del usuario según una jerarquía estricta de seguridad y contexto."""
    # 0. Exclusión activa irrevocable en la sesión (regla suprema de seguridad)
    if context is not None and context.is_do_not_contact:
        return CommercialIntent.DO_NOT_CONTACT, 1.0, ["dnc_permanent_override"]

    # 1. Petición expresa de NO contacto / baja (máxima prioridad legal y comercial)
    is_contradictory_dnc = bool(
        re.search(r"\bno\s+quiero\s+dejar\s+de\s+(recibir|tener|admitir)\b", cleaned_text)
    )
    if not is_contradictory_dnc:
        dnc_matches = _matches_any(cleaned_text, _PATTERNS_DO_NOT_CONTACT)
        if dnc_matches:
            return CommercialIntent.DO_NOT_CONTACT, 1.0, dnc_matches

    # 2. Retirada de interés previa
    has_prior_interest = context is not None and (
        context.interest_expressed or context.meeting_requested or context.proposal_requested
    )
    withdrawal_matches = _matches_any(cleaned_text, _PATTERNS_INTEREST_WITHDRAWAL)
    if withdrawal_matches and (has_prior_interest or re.search(r"\b(ya\s+no|arrepentido|cancela)\b", cleaned_text)):
        return CommercialIntent.INTEREST_WITHDRAWAL, 0.95, withdrawal_matches

    # 3. Transferencia a Hugo o persona humana
    human_matches = _matches_any(cleaned_text, _PATTERNS_TRANSFER_HUMAN)
    if human_matches:
        return CommercialIntent.HUMAN_HANDOFF_REQUESTED, 0.95, human_matches

    # 4. Despedida explícita
    is_contradictory_farewell = bool(
        re.search(r"\bno\s+(quiero\s+)?(terminar|colgar|acabar|irte)\b", cleaned_text)
    )
    if not is_contradictory_farewell:
        farewell_matches = _matches_any(cleaned_text, _PATTERNS_FAREWELL)
        if farewell_matches:
            return CommercialIntent.FAREWELL, 0.95, farewell_matches

    # 5. Petición de rellamada específica (antes de rechazo, porque puede contener "no interesa ahora")
    callback_matches = _matches_any(cleaned_text, _PATTERNS_CALLBACK_REQUEST)
    if callback_matches:
        return CommercialIntent.CALLBACK_REQUEST, 0.92, callback_matches

    # 6. Rechazo comercial suave
    rejection_matches = _matches_any(cleaned_text, _PATTERNS_SOFT_REJECTION)
    if rejection_matches:
        return CommercialIntent.SOFT_REJECTION, 0.90, rejection_matches

    # 7. Privacidad y tratamiento de datos
    privacy_matches = _matches_any(cleaned_text, _PATTERNS_PRIVACY_INQUIRY)
    if privacy_matches:
        return CommercialIntent.PRIVACY_INQUIRY, 0.95, privacy_matches

    # 8. Ocupado / falta de tiempo
    busy_matches = _matches_any(cleaned_text, _PATTERNS_BUSY_CALL_LATER)
    if busy_matches:
        return CommercialIntent.BUSY_CALL_LATER, 0.90, busy_matches

    # 9. Competidor existente
    competitor_matches = _matches_any(cleaned_text, _PATTERNS_EXISTING_COMPETITOR)
    if competitor_matches:
        return CommercialIntent.EXISTING_COMPETITOR, 0.90, competitor_matches

    # 10. Preguntas de precio / tarifas
    price_matches = _matches_any(cleaned_text, _PATTERNS_PRICE_INQUIRY)
    if price_matches:
        return CommercialIntent.PRICE_INQUIRY, 0.90, price_matches

    # 11. Integraciones técnicas
    tech_matches = _matches_any(cleaned_text, _PATTERNS_TECHNICAL_INTEGRATION)
    if tech_matches:
        return CommercialIntent.TECHNICAL_INTEGRATION, 0.90, tech_matches

    # 12. Disponibilidad de agenda
    sched_matches = _matches_any(cleaned_text, _PATTERNS_SCHEDULE_AVAILABILITY)
    if sched_matches:
        return CommercialIntent.SCHEDULE_AVAILABILITY, 0.90, sched_matches

    # 13. Petición de reunión
    meeting_matches = _matches_any(cleaned_text, _PATTERNS_MEETING_REQUEST)
    if meeting_matches:
        return CommercialIntent.MEETING_REQUEST, 0.95, meeting_matches

    # 14. Expresión de interés / solicitud de propuesta
    interest_matches = _matches_any(cleaned_text, _PATTERNS_EXPRESS_INTEREST)
    if interest_matches:
        return CommercialIntent.EXPRESS_INTEREST, 0.90, interest_matches

    # 15. Cualificación de web: ¿tiene o no tiene web?
    no_web_matches = _matches_any(cleaned_text, _PATTERNS_HAS_NO_WEBSITE)
    if no_web_matches or (context and context.last_question_asked == "has_website" and cleaned_text in ("no", "no tenemos", "no la verdad", "que va")):
        return CommercialIntent.HAS_NO_WEBSITE, 0.90, no_web_matches or ["context_no_website"]

    web_matches = _matches_any(cleaned_text, _PATTERNS_HAS_WEBSITE)
    if web_matches or (context and context.last_question_asked == "has_website" and cleaned_text in ("si", "si tenemos", "si ya tenemos")):
        return CommercialIntent.HAS_WEBSITE, 0.90, web_matches or ["context_has_website"]

    # 16. Confirmación de decisor
    decision_matches = _matches_any(cleaned_text, _PATTERNS_DECISION_MAKER_CONFIRMATION)
    if decision_matches or (context and context.stage == CommercialStage.OPENING and cleaned_text in ("si", "soy yo", "con el hablas", "dime", "si dime")):
        return CommercialIntent.DECISION_MAKER_CONFIRMATION, 0.90, decision_matches or ["context_decision_maker"]

    # Bloqueo de reactivación: si ya hubo rechazo o la sesión está terminada, ninguna
    # frase ambigua (afirmaciones, saludos) debe reactivar el discurso de venta.
    if context is not None and (context.is_rejected or context.is_finished):
        return CommercialIntent.SOFT_REJECTION, 0.85, ["post_rejection_no_push"]

    # 17. Respuestas afirmativas contextuales ("sí, cuéntame")
    affirmative_matches = _matches_any(cleaned_text, _PATTERNS_AFFIRMATIVE_CONTINUE)
    if affirmative_matches:
        return CommercialIntent.AFFIRMATIVE_CONTINUE, 0.90, affirmative_matches

    # 18. Información de servicios
    service_matches = _matches_any(cleaned_text, _PATTERNS_SERVICE_INFO)
    if service_matches:
        return CommercialIntent.SERVICE_INFO, 0.90, service_matches

    # 19. Información desconocida de la empresa
    unknown_matches = _matches_any(cleaned_text, _PATTERNS_UNKNOWN_INFO)
    if unknown_matches:
        return CommercialIntent.UNKNOWN_INFO, 0.85, unknown_matches

    # 20. Saludo / presentación
    greeting_matches = _matches_any(cleaned_text, _PATTERNS_GREETING_PRESENTATION)
    if greeting_matches:
        return CommercialIntent.GREETING_PRESENTATION, 0.85, greeting_matches

    # 21. Si estamos recopilando requerimientos y el usuario responde a la pregunta de actividad/features
    if context is not None and context.stage == CommercialStage.COLLECT_REQUIREMENTS:
        return CommercialIntent.EXPRESS_INTEREST, 0.80, ["context_collect_requirements"]

    # 22. Fallback por defecto
    return CommercialIntent.FALLBACK_CLARIFICATION, 0.50, ["fallback_default"]


# --- GENERACIÓN DE RESPUESTA Y SEGURIDAD COMERCIAL ---

def generate_response_text(
    intent: CommercialIntent,
    context: ConversationContext | None = None,
    config: CommercialConfig | None = None,
) -> str:
    """Genera la respuesta comercial en el tono conversacional y cercano de Hugo."""
    cfg = config if config is not None else DEFAULT_COMMERCIAL_CONFIG

    if intent == CommercialIntent.DO_NOT_CONTACT:
        if context is not None and context.is_do_not_contact and context.turn_count > 0:
            return (
                "Su solicitud de no contacto ya quedó registrada en esta sesión y no volveremos a contactarle. "
                "Esta conversación está concluida. Que tenga un buen día."
            )
        return (
            "Entendido. He registrado en esta sesión su petición de no volver a contactarle "
            "y no continuaremos la llamada. Disculpe las molestias y que tenga un buen día."
        )

    if intent == CommercialIntent.INTEREST_WITHDRAWAL:
        return (
            "Entendido perfectamente. Tomo nota en esta sesión de que prefieres no continuar "
            "y cancelamos la propuesta. Muchas gracias por tu tiempo y que vaya todo genial."
        )

    if intent == CommercialIntent.FAREWELL:
        return "¡Perfecto! Muchas gracias por tu tiempo y que vaya todo genial. ¡Hasta luego!"

    if intent in (CommercialIntent.TRANSFER_HUMAN, CommercialIntent.HUMAN_HANDOFF_REQUESTED):
        if context is not None:
            context.human_handoff_requested = True
            context.stage = CommercialStage.HUMAN_HANDOFF_REQUESTED
        return (
            f"¡Perfecto! Me apunto la solicitud para pasarte con {cfg.agent_name}. "
            "Como soy un asistente virtual en pruebas, todavía no tengo transferencia directa de llamada, "
            f"pero {cfg.agent_name} se pondrá en contacto contigo para hablarlo directamente. Muchas gracias."
        )

    if intent == CommercialIntent.DECISION_MAKER_CONFIRMATION:
        if context is not None:
            context.is_decision_maker = True
            context.has_presented_self = True
            context.last_question_asked = "has_website"
            context.stage = CommercialStage.QUALIFY_WEBSITE
        return (
            f"¡Hola, qué tal! Soy el asistente virtual de {cfg.agent_name}. Estamos ayudando a negocios de la zona "
            "a tener una web profesional y quería preguntarte una cosa rápida: ¿tenéis página web propia ahora mismo?"
        )

    if intent == CommercialIntent.HAS_NO_WEBSITE:
        if context is not None:
            context.has_own_website = False
            context.last_question_asked = "proposal_or_hugo"
            context.stage = CommercialStage.QUALIFY_INTEREST
        return (
            f"Vale, justo por eso te contactamos. {cfg.agent_name} prepara webs para que los negocios puedan enseñar "
            "sus servicios, fotos y ubicación, y para que los clientes puedan contactarles fácilmente por WhatsApp o por otros medios. "
            f"¿Te interesaría ver una propuesta para vuestro negocio o prefieres hablar directamente con {cfg.agent_name}?"
        )

    if intent == CommercialIntent.HAS_WEBSITE:
        if context is not None:
            context.has_own_website = True
            context.last_question_asked = "proposal_or_hugo"
            context.stage = CommercialStage.QUALIFY_INTEREST
        return (
            f"¡Ah, genial que ya tengáis web! {cfg.agent_name} también ayuda a rediseñarlas, adaptarlas a móviles "
            "o actualizarlas si queréis mejorarla. ¿Te interesaría ver una propuesta de mejora o prefieres hablar con él?"
        )

    if intent == CommercialIntent.AFFIRMATIVE_CONTINUE:
        if context is not None:
            if context.last_question_asked == "has_website":
                return "Vale, ¿tenéis página web propia ahora mismo o sería empezar desde cero?"
            if context.last_question_asked in ("proposal_or_hugo", None):
                context.proposal_requested = True
                context.last_question_asked = "activity"
                context.stage = CommercialStage.COLLECT_REQUIREMENTS
                return (
                    f"¡Genial! Para no hacerte perder tiempo, te hago un par de preguntas rápidas y así {cfg.agent_name} "
                    "puede orientarte con el precio. ¿A qué os dedicáis exactamente en el negocio?"
                )
            if context.last_question_asked == "confirm_closing":
                context.is_finished = True
                context.stage = CommercialStage.FINISHED
                return (
                    f"¡Estupendo! Le paso la nota a {cfg.agent_name} con lo que hemos hablado para que se ponga en contacto contigo "
                    "y ver los siguientes pasos. ¡Muchas gracias por tu tiempo y que tengas buen día!"
                )
        return (
            f"¡Genial! Te cuento rápido: {cfg.agent_name} ayuda a negocios locales a crear su página web "
            "para que los clientes os contacten fácilmente por WhatsApp. ¿Tenéis web propia ahora mismo?"
        )

    if intent == CommercialIntent.SOFT_REJECTION:
        if context is not None and context.is_rejected and context.turn_count > 0:
            return (
                "Entendido. Respetamos tu decisión de no continuar con la propuesta. "
                "Quedamos a tu disposición si en el futuro necesitas consultar algo. Que tenga un buen día."
            )
        return (
            "Vale, sin problema. Muchas gracias por tu tiempo y por atenderme. "
            "Respetamos tu respuesta y que tenga un buen día. ¡Hasta luego!"
        )

    if intent == CommercialIntent.TECHNICAL_INTEGRATION:
        return (
            "Este prototipo se encuentra actualmente en fase de validación de voz y no dispone de integraciones "
            "ni APIs activas con software de terceros. Cualquier requerimiento técnico debe ser evaluado con los responsables del proyecto."
        )

    if intent == CommercialIntent.SCHEDULE_AVAILABILITY:
        return (
            "Como asistente virtual en pruebas no dispongo de agenda en tiempo real del equipo. "
            "Indícame qué día o franja te vendría bien y se la anotamos a Hugo como propuesta orientativa."
        )

    if intent == CommercialIntent.MEETING_REQUEST:
        return (
            f"Con mucho gusto. Tomo nota de tu propuesta de reunión para comentársela a {cfg.agent_name}. "
            "¿Qué día y franja te vendría mejor? "
            f"El equipo revisará la agenda y le confirmará la disponibilidad, ya que esta anotación queda como propuesta y no como cita fijada."
        )

    if intent == CommercialIntent.EXPRESS_INTEREST:
        if context is not None:
            context.proposal_requested = True
            if context.last_question_asked == "activity":
                context.last_question_asked = "features"
                return (
                    "¡Qué bueno! ¿Y qué te gustaría que pudieran hacer los clientes desde la web: "
                    "ver vuestros servicios, escribiros por WhatsApp, reservar o algo más?"
                )
            if context.last_question_asked == "features":
                context.last_question_asked = "content"
                return "Perfecto. ¿Y tenéis fotos y textos del negocio o habría que preparar parte del contenido?"
            if context.last_question_asked == "content":
                context.last_question_asked = "confirm_closing"
                context.stage = CommercialStage.CLOSING
                return (
                    f"Por lo que me cuentas, creo que podría encajaros genial. {cfg.agent_name} puede prepararos una web "
                    f"con las características que hemos hablado. El precio orientativo es de {int(cfg.starting_price)} €, "
                    "incluyendo web adaptada a móviles, sección de servicios, ubicación y contacto directo por WhatsApp. "
                    f"¿Te gustaría que {cfg.agent_name} te contacte para ver los siguientes pasos?"
                )
            context.last_question_asked = "activity"
            context.stage = CommercialStage.COLLECT_REQUIREMENTS

        return (
            f"¡Genial! Para no hacerte perder tiempo, te hago un par de preguntas rápidas y así {cfg.agent_name} "
            "puede orientarte con el precio. También podemos enviar los detalles por correo electrónico si prefieres. "
            "¿A qué os dedicáis exactamente?"
        )

    if intent == CommercialIntent.PRICE_INQUIRY:
        return (
            f"El precio inicial orientativo para una web básica es de {int(cfg.starting_price)} €. "
            "No disponemos de una tarifa fija estándar para todo porque si hacen falta extras como tienda online "
            f"o reservas complejas, {cfg.agent_name} prepara un presupuesto personalizado. "
            f"¿Te gustaría ver una propuesta básica o prefieres hablar con él?"
        )

    if intent == CommercialIntent.BUSY_CALL_LATER:
        return (
            "Entiendo perfectamente que te pille en un mal momento. "
            "¿Prefieres que intentemos contactarte mañana o en alguna otra franja que te venga mejor?"
        )

    if intent == CommercialIntent.CALLBACK_REQUEST:
        return (
            "De acuerdo, tomo nota de su preferencia de horario en esta simulación. "
            "Muchas gracias por tu atención y que tengas un buen día."
        )

    if intent == CommercialIntent.EXISTING_COMPETITOR:
        return (
            "Entendido, es una excelente referencia que ya cuenten con una solución operativa. "
            "Agradezco que me lo indiques para no interferir en vuestro trabajo. Muchas gracias."
        )

    if intent == CommercialIntent.SERVICE_INFO:
        return (
            f"Hola, soy el asistente virtual de {cfg.agent_name}. Ayudamos a negocios locales con su página web "
            "para que puedan enseñar sus servicios, fotos y ubicación, y que los clientes os contacten por WhatsApp. "
            "Para orientarte mejor, ¿qué tipo de proceso o servicio te gustaría que mostremos en tu web?"
        )

    if intent == CommercialIntent.GREETING_PRESENTATION:
        if context is not None and context.has_presented_self:
            return f"¡Hola de nuevo! Dime, ¿en qué te puede ayudar {cfg.agent_name}?"

        if context is not None:
            context.has_presented_self = True
            context.last_question_asked = "is_decision_maker"
            context.stage = CommercialStage.IDENTIFY_DECISION_MAKER

        return f"Hola, buenas. Soy el asistente virtual de {cfg.agent_name}. ¿Está la persona que lleva el negocio?"

    if intent == CommercialIntent.UNKNOWN_INFO:
        return (
            "Disculpe, no dispongo de ese dato específico en este prototipo. "
            f"Tomo nota de tu consulta para trasladársela a {cfg.agent_name}."
        )

    if intent == CommercialIntent.UNINTELLIGIBLE:
        return (
            "Disculpe, no he podido escucharle con claridad. "
            "¿Podrías repetir lo que me decías, por favor?"
        )

    # Fallback por defecto
    return (
        f"Gracias por tu mensaje. Para poder orientarle en esta prueba técnica, "
        f"¿le gustaría conocer nuestros servicios de páginas web con {cfg.agent_name}, hablar con él o prefieres no continuar?"
    )


def generate_commercial_response(
    transcribed_text: str,
    context: ConversationContext | None = None,
    config: CommercialConfig | None = None,
) -> CommercialResponse:
    """Función de entrada principal que procesa la transcripción, actualiza el estado y emite la respuesta."""
    ctx = context if context is not None else ConversationContext()
    cfg = config if config is not None else DEFAULT_COMMERCIAL_CONFIG

    # Manejo de entrada vacía o ininteligible
    if not transcribed_text or not transcribed_text.strip():
        resp_text = generate_response_text(CommercialIntent.UNINTELLIGIBLE, ctx, cfg)
        ctx.record_turn(transcribed_text, resp_text, CommercialIntent.UNINTELLIGIBLE)
        return CommercialResponse(
            intent=CommercialIntent.UNINTELLIGIBLE,
            response_text=resp_text,
            confidence=1.0,
            matched_patterns=["empty_input"],
            is_do_not_contact=ctx.is_do_not_contact,
            context=ctx,
        )

    raw_lower = transcribed_text.strip().lower()
    has_letters = any(c.isalnum() for c in raw_lower)
    if raw_lower in _NOISE_TOKENS or not has_letters or len(raw_lower) < 3:
        resp_text = "Disculpe, no he recibido un mensaje claro. ¿Podría indicarme en qué puedo orientarle?"
        ctx.record_turn(transcribed_text, resp_text, CommercialIntent.UNINTELLIGIBLE)
        return CommercialResponse(
            intent=CommercialIntent.UNINTELLIGIBLE,
            response_text=resp_text,
            confidence=0.9,
            matched_patterns=["noise_or_too_short"],
            is_do_not_contact=ctx.is_do_not_contact,
            context=ctx,
        )

    cleaned = _clean_text(transcribed_text)
    intent, confidence, matched_patterns = classify_intent(cleaned, ctx)
    response_text = generate_response_text(intent, ctx, cfg)

    ctx.record_turn(transcribed_text, response_text, intent)

    return CommercialResponse(
        intent=intent,
        response_text=response_text,
        confidence=confidence,
        matched_patterns=matched_patterns,
        is_do_not_contact=ctx.is_do_not_contact,
        context=ctx,
    )
