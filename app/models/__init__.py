from .user import User  # noqa: F401
from .vehicle import Vehicle  # noqa: F401
from .consultation import Consultation  # noqa: F401
from .audit_log import AuditLog  # noqa: F401
from .consultation_pdf import ConsultationPDF  # noqa: F401
from .chat_thread_pdf import ChatThreadPDF  # noqa: F401
from .user_token_usage import UserTokenUsage  # noqa: F401
from .ai_provider import AIProvider, WorkshopAIProvider, AIProviderType  # noqa: F401
from .prompt import GlobalPrompt  # noqa: F401

# Import from new module structure
from app.workshops.models import Workshop, WorkshopMember  # noqa: F401
from app.chat.models import ChatThread, ChatMessage  # noqa: F401


