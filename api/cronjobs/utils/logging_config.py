"""
Configuración centralizada de logging para cronjobs.

IMPORTANTE: Esta configuración mantiene compatibilidad con print() existente
mientras permite usar logging estructurado.
"""
import logging
import sys
from typing import Optional

# Configurar logger para cronjobs
logger = logging.getLogger('cronjobs')
logger.setLevel(logging.INFO)

# Handler para consola (stdout) - compatible con logs actuales
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)

# Formato estructurado pero legible
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
console_handler.setFormatter(formatter)

# Agregar handler solo si no existe (evitar duplicados)
if not logger.handlers:
    logger.addHandler(console_handler)

# Logger específico para telemetría
telemetry_logger = logging.getLogger('cronjobs.telemetry')
telemetry_logger.setLevel(logging.INFO)
if not telemetry_logger.handlers:
    telemetry_logger.addHandler(console_handler)

# Logger específico para DGA
dga_logger = logging.getLogger('cronjobs.dga')
dga_logger.setLevel(logging.INFO)
if not dga_logger.handlers:
    dga_logger.addHandler(console_handler)


def log_info(message: str, logger_name: str = 'cronjobs'):
    """
    Logging de información (reemplazo de print() para mensajes informativos).
    
    Args:
        message: Mensaje a loguear
        logger_name: Nombre del logger a usar
    """
    logger_instance = logging.getLogger(logger_name)
    logger_instance.info(message)


def log_warning(message: str, logger_name: str = 'cronjobs'):
    """
    Logging de advertencias.
    
    Args:
        message: Mensaje a loguear
        logger_name: Nombre del logger a usar
    """
    logger_instance = logging.getLogger(logger_name)
    logger_instance.warning(message)


def log_error(message: str, exception: Optional[Exception] = None, logger_name: str = 'cronjobs'):
    """
    Logging de errores.
    
    Args:
        message: Mensaje a loguear
        exception: Excepción opcional a incluir
        logger_name: Nombre del logger a usar
    """
    logger_instance = logging.getLogger(logger_name)
    if exception:
        logger_instance.error(f"{message}: {exception}", exc_info=True)
    else:
        logger_instance.error(message)

