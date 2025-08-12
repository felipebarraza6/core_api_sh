#!/usr/bin/env python3
"""
Configuración de alertas - MODIFICA AQUÍ TUS CONFIGURACIONES
"""

# CONFIGURACIÓN DE ALERTAS
ALERT_CONFIG = {
    # Configuración por punto: ID -> [correos]
    "points_emails": {
        1: ["soporte@smarthydro.app"],
        2: ["constansa.hidd@iansa.cl", "soporte@smarthydro.app"],
        # Agregar más puntos aquí:
        # 5: ["correo1@empresa.com", "correo2@empresa.com"],
        # 10: ["admin@empresa.com"],
    },
    # Configuración de umbrales
    "dga_queue_threshold": 5,  # Si hay más de 5 registros en cola DGA
    "disconnection_threshold": 1,  # Si days_not_conection > 1
    # Configuración de correo cPanel
    "smtp_server": "s1042.use1.mysecurecloudhost.com",  # Servidor SMTP de cPanel
    "smtp_port": 465,
    "smtp_user": "notify@smarthydro.app",
    "smtp_password": "notify.2025",
}

# MAPEO DE TIPOS DE ALERTA DEL SISTEMA A VALORES DEL MODELO
# Usamos los valores existentes del modelo para no alterar la DB
ALERT_TYPE_MAPPING = {
    "DGA_QUEUE": "MAX",  # Cola DGA -> MAX (mas)
    "DISCONNECTION": "MIN",  # Desconexión -> MIN (menos)
    "RECONNECTION": "EQUALS",  # Reconexión -> EQUALS (igual)
}

"""
INSTRUCCIONES DE CONFIGURACIÓN:

1. PUNTOS Y CORREOS:
   - Cada punto tiene sus propios correos de alerta
   - Formato: ID: [correo1, correo2, correo3]
   - Ejemplo: 1: ["admin@empresa.com", "tecnico@empresa.com"]

2. UMBRALES:
   - "dga_queue_threshold": Cuántos registros en cola DGA antes de alertar
   - "disconnection_threshold": Cuántos días desconectado antes de alertar

3. CONFIGURACIÓN DE CORREO:
   - Ya configurado para tu servidor cPanel
   - Servidor: mail.smarthydro.app
   - Usuario: notify@smarthydro.app
   - Contraseña: notifiy.2025

EJEMPLO DE CONFIGURACIÓN:
ALERT_CONFIG = {
    "points_emails": {
        1: ["admin@miempresa.com", "tecnico@miempresa.com"],
        5: ["admin@miempresa.com"],
        10: ["soporte@miempresa.com", "emergencias@miempresa.com"],
    },
    "dga_queue_threshold": 3,
    "disconnection_threshold": 1,
    "smtp_server": "mail.smarthydro.app",
    "smtp_port": 587,
    "smtp_user": "notify@smarthydro.app",
    "smtp_password": "notifiy.2025"
}
"""
