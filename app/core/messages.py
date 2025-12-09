"""Spanish error messages and user-facing text for the backend."""

# Authentication messages
AUTH_INVALID_CREDENTIALS = "Credenciales inválidas"
AUTH_USER_NOT_FOUND = "Usuario no encontrado"
AUTH_USER_INACTIVE = "Usuario inactivo"
AUTH_TOKEN_EXPIRED = "Token expirado"
AUTH_TOKEN_INVALID = "Token inválido"
AUTH_REFRESH_TOKEN_INVALID = "Token de actualización inválido"
AUTH_REFRESH_TOKEN_PAYLOAD_INVALID = "Payload del token de actualización inválido"
AUTH_REFRESH_TOKEN_REVOKED = "El token de actualización ha sido rotado o revocado"
AUTH_USER_ID_INVALID = "Formato de ID de usuario inválido"
AUTH_USER_NOT_FOUND_OR_INACTIVE = "Usuario no encontrado o inactivo"
AUTH_INSUFFICIENT_PERMISSIONS = "Permisos insuficientes"
AUTH_EMAIL_NOT_VERIFIED = "Correo electrónico no verificado. Por favor verifica tu correo antes de iniciar sesión."
AUTH_LOGOUT_SUCCESS = "Sesión cerrada"

# Registration messages
REG_USERNAME_REQUIRED = "El nombre de usuario es requerido"
REG_EMAIL_REQUIRED = "El correo electrónico es requerido"
REG_PASSWORD_REQUIRED = "La contraseña es requerida"
REG_USERNAME_EXISTS = "El nombre de usuario ya existe"
REG_EMAIL_EXISTS = "El correo electrónico ya está registrado"
REG_PASSWORD_TOO_SHORT = "La contraseña debe tener al menos 12 caracteres"
REG_PASSWORD_COMPLEXITY = "La contraseña debe contener mayúsculas, minúsculas, números y caracteres especiales"
REG_SUCCESS = "Usuario registrado exitosamente. Por favor verifica tu correo electrónico."
REG_EMAIL_VERIFICATION_SENT = "Correo de verificación enviado"

# Email verification
EMAIL_VERIFICATION_SUCCESS = "Correo electrónico verificado exitosamente. Tu cuenta ahora está activa."
EMAIL_VERIFICATION_FAILED = "Token de verificación inválido o expirado"
EMAIL_VERIFICATION_EXPIRED = "El token de verificación ha expirado. Por favor solicita uno nuevo."
EMAIL_VERIFICATION_ALREADY_VERIFIED = "Este correo electrónico ya ha sido verificado"
EMAIL_VERIFICATION_RESENT = "Si existe una cuenta con este correo, se ha enviado un enlace de verificación."
EMAIL_REQUIRED = "El correo electrónico es requerido"
EMAIL_ALREADY_VERIFIED = "El correo electrónico ya está verificado"

# Workshop messages
WORKSHOP_NOT_FOUND = "Taller no encontrado"
WORKSHOP_ACCESS_DENIED = "No tienes acceso a este taller"
WORKSHOP_NAME_REQUIRED = "El nombre del taller es requerido"
WORKSHOP_CREATED = "Taller creado exitosamente"
WORKSHOP_UPDATED = "Taller actualizado exitosamente"
WORKSHOP_DELETED = "Taller eliminado exitosamente"

# Vehicle messages
VEHICLE_NOT_FOUND = "Vehículo no encontrado"
VEHICLE_LICENSE_PLATE_REQUIRED = "La placa del vehículo es requerida"
VEHICLE_CREATED = "Vehículo creado exitosamente"
VEHICLE_UPDATED = "Vehículo actualizado exitosamente"
VEHICLE_DELETED = "Vehículo eliminado exitosamente"
VEHICLE_ALREADY_EXISTS = "Ya existe un vehículo con esta placa en este taller"

# Chat messages
CHAT_THREAD_NOT_FOUND = "Sesión de chat no encontrada"
CHAT_THREAD_ACCESS_DENIED = "No tienes acceso a esta sesión"
CHAT_MESSAGE_REQUIRED = "El contenido del mensaje es requerido"
CHAT_THREAD_CREATED = "Sesión creada exitosamente"
CHAT_MESSAGE_SENT = "Mensaje enviado exitosamente"
CHAT_THREAD_DELETED = "Sesión eliminada exitosamente"

# Token messages
TOKEN_LIMIT_EXCEEDED = "Límite de tokens excedido. Por favor intenta más tarde o contacta a tu administrador."
TOKEN_WORKSHOP_LIMIT_EXCEEDED = "Límite mensual de tokens del taller excedido"
TOKEN_USER_LIMIT_EXCEEDED = "Límite diario de tokens del usuario excedido"
TOKEN_INSUFFICIENT = "Tokens insuficientes disponibles"

# AI Service messages
AI_SERVICE_UNAVAILABLE = "Servicio de IA no disponible"
AI_SERVICE_CONFIG_ERROR = "Error de configuración del servicio de IA. Por favor contacta a tu administrador."
AI_SERVICE_API_KEY_MISSING = "Clave API de OpenAI no configurada"

# Database messages
DB_CONNECTION_ERROR = "Error de conexión a la base de datos. Por favor intenta de nuevo."
DB_QUERY_ERROR = "Error al consultar la base de datos"

# Validation messages
VALIDATION_REQUIRED = "Este campo es requerido"
VALIDATION_INVALID_FORMAT = "Formato inválido"
VALIDATION_INVALID_EMAIL = "Correo electrónico inválido"
VALIDATION_INVALID_UUID = "ID inválido"

# General error messages
ERROR_INTERNAL_SERVER = "Error interno del servidor"
ERROR_NOT_FOUND = "Recurso no encontrado"
ERROR_PERMISSION_DENIED = "No tienes permiso para realizar esta acción"
ERROR_BAD_REQUEST = "Solicitud inválida"
ERROR_TIMEOUT = "Tiempo de espera agotado. Por favor intenta de nuevo."

# PDF messages
PDF_GENERATION_FAILED = "No se pudo generar el PDF"
PDF_GENERATION_SUCCESS = "PDF generado exitosamente"
PDF_DOWNLOAD_FAILED = "No se pudo descargar el PDF"

# File upload messages
FILE_UPLOAD_FAILED = "No se pudo subir el archivo"
FILE_TOO_LARGE = "El archivo es demasiado grande"
FILE_INVALID_TYPE = "Tipo de archivo inválido"

# Success messages
SUCCESS_OPERATION = "Operación completada exitosamente"
SUCCESS_UPDATED = "Actualizado exitosamente"
SUCCESS_DELETED = "Eliminado exitosamente"
SUCCESS_CREATED = "Creado exitosamente"

