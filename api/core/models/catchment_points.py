"""Client Profile."""

from django.db import models

from .users import User
from .utils import ModelApi


class Client(ModelApi):
    """Client Model for Catchment Points."""

    name = models.CharField(max_length=300, verbose_name="Nombre")
    rut = models.CharField(max_length=300, verbose_name="Rut")
    address = models.CharField(max_length=300, verbose_name="Direccion")
    phone = models.CharField(max_length=300, verbose_name="Telefono")
    email = models.CharField(max_length=300, verbose_name="Correo")

    class Meta:
        """Meta data client"""

        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"

    def __str__(self):
        return f"{self.name}"


class ProjectCatchments(ModelApi):
    """Project Catchments Model."""

    name = models.CharField(max_length=300, verbose_name="Nombre")
    client = models.ForeignKey(
        Client, blank=True, null=True, on_delete=models.CASCADE, verbose_name="Cliente"
    )
    code_internal = models.CharField(
        max_length=300, blank=True, null=True, verbose_name="Codigo interno"
    )

    class Meta:
        """Meta data project catchments"""

        verbose_name = "Proyecto"
        verbose_name_plural = "Proyectos"

    def __str__(self):
        return f"{self.name}"


class CatchmentPoint(ModelApi):
    """Catchment points model."""

    project = models.ForeignKey(
        ProjectCatchments,
        related_name="catchment_points",
        on_delete=models.CASCADE,
        verbose_name="Proyecto",
    )
    title = models.CharField(
        max_length=200, blank=True, null=True, verbose_name="Nombre"
    )

    owner_user = models.ForeignKey(
        User,
        related_name="owned_catchment_points",
        on_delete=models.CASCADE,
        verbose_name="Propietario",
    )
    users_viewers = models.ManyToManyField(
        User, verbose_name="usuario", related_name="viewed_catchment_points", blank=True
    )

    is_thethings = models.BooleanField(default=False, verbose_name="Nettra")
    is_tdata = models.BooleanField(default=False, verbose_name="Twin")
    is_novus = models.BooleanField(default=False, verbose_name="Novus")

    lat = models.CharField(
        max_length=300, blank=True, null=True, verbose_name="latitud"
    )

    lon = models.CharField(
        max_length=300, blank=True, null=True, verbose_name="longitud"
    )

    FRECUENCY_OPTIONS = [
        ("1", "1 minuto"),
        ("5", "5 minutos"),
        ("10", "10 minutos"),
        ("60", "60 minutos"),
    ]

    frecuency = models.CharField(
        blank=True,
        null=True,
        max_length=300,
        choices=FRECUENCY_OPTIONS,
        verbose_name="Frecuencia",
        default="60",
    )

    class Meta:
        """Meta data catchment points"""

        verbose_name = "Punto de captacion"
        verbose_name_plural = "Puntos de captacion"

    def __str__(self):
        return f"{self.title} - {self.owner_user}"


class ProfileIkoluCatchment(ModelApi):
    """Ikolu Status Profile."""

    point_catchment = models.ForeignKey(
        CatchmentPoint,
        related_name="ikolu_profiles",
        on_delete=models.CASCADE,
        verbose_name="Punto de captacion",
    )
    entry_by_form = models.BooleanField(
        default=False, verbose_name="Ingreso por formulario"
    )
    m1 = models.BooleanField(default=True, verbose_name="MODULO: Mi Pozo")

    m2 = models.BooleanField(default=False, verbose_name="MODULO: DGA")

    SUBSCRIPTIONS_CHOICES = [
        ("MENSUAL", "mensual"),
        ("TRIMESTRAL", "trimestral"),
        ("SEMESTRAL", "semestral"),
        ("ANUAL", "anual"),
    ]

    m3 = models.BooleanField(default=False, verbose_name="MODULO: Datos y reportes")
    m3_start_subscription = models.DateField(
        blank=True,
        null=True,
        verbose_name="Fecha inicio suscripción MODULO: Datos y reportes",
    )
    m3_type_subscriptions = models.CharField(
        max_length=300,
        blank=True,
        null=True,
        choices=SUBSCRIPTIONS_CHOICES,
        verbose_name="Tipo de suscripción MODULO: Datos y reportes",
    )

    m4 = models.BooleanField(default=False, verbose_name="MODULO: Graficos")
    m4_start_subscription = models.DateField(
        blank=True, null=True, verbose_name="Fecha inicio suscripción MODULO: Graficos"
    )
    m4_type_subscriptions = models.CharField(
        max_length=300,
        blank=True,
        null=True,
        choices=SUBSCRIPTIONS_CHOICES,
        verbose_name="Tipo de suscripción MODULO: Graficos",
    )

    m5 = models.BooleanField(default=False, verbose_name="MODULO: Indicadores")
    m5_start_subscription = models.DateField(
        blank=True,
        null=True,
        verbose_name="Fecha inicio suscripción MODULO: Indicadores",
    )
    m5_type_subscriptions = models.CharField(
        max_length=300,
        blank=True,
        null=True,
        choices=SUBSCRIPTIONS_CHOICES,
        verbose_name="Tipo de suscripción MODULO: Indicadores",
    )

    m6 = models.BooleanField(default=False, verbose_name="MODULO: Alarmas")
    m6_start_subscription = models.DateField(
        blank=True, null=True, verbose_name="Fecha inicio suscripción MODULO: Alarmas"
    )
    m6_type_subscriptions = models.CharField(
        max_length=300,
        blank=True,
        null=True,
        choices=SUBSCRIPTIONS_CHOICES,
        verbose_name="Tipo de suscripción MODULO: Alarmas",
    )

    m7 = models.BooleanField(default=False, verbose_name="MODULO: Documentos")
    m7_start_subscription = models.DateField(
        blank=True,
        null=True,
        verbose_name="Fecha inicio suscripción MODULO: Documentos",
    )
    m7_type_subscriptions = models.CharField(
        max_length=300,
        blank=True,
        null=True,
        choices=SUBSCRIPTIONS_CHOICES,
        verbose_name="Tipo de suscripción MODULO: Documentos",
    )

    class Meta:
        """Meta data profile ikolu"""

        verbose_name = "Perfil Ikolu"
        verbose_name_plural = "Perfiles Ikolu"

    def __str__(self):
        return f"{self.point_catchment}"


class NotificationsCatchment(ModelApi):
    """Notifications Model."""

    point_catchment = models.ForeignKey(
        CatchmentPoint,
        related_name="notifications",
        on_delete=models.CASCADE,
        verbose_name="Punto de captacion",
    )
    title = models.CharField(max_length=300, verbose_name="Titulo")
    message = models.CharField(max_length=1300, verbose_name="Mensaje")
    VARIABLES_CHOICES = [
        ("NIVEL", "nivel"),
        ("CAUDAL", "caudal"),
        ("CAUDAL PROMEDIO", "caudal_promedio((diff/3600)*1000)"),
        ("TOTALIZADO", "totalizado"),
        ("TODOS", "todos"),
    ]
    TYPE_NOTIFICATION_CHOICES = [
        ("INFO", "Informativo"),
        ("WARNING", "Advertencia"),
        ("ALERT", "Alerta"),
        ("CRITICAL", "Crítico"),
        ("SUPPORT", "Soporte"),
    ]
    TYPE_ALERT_CHOICES = [
        ("MAX", "mas"),
        ("MIN", "menos"),
        ("EQUALS", "igual"),
    ]
    type_variable = models.CharField(
        max_length=300,
        choices=VARIABLES_CHOICES,
        verbose_name="Tipo variable",
        blank=True,
        null=True,
    )

    value = models.IntegerField(default=0, verbose_name="Valor")
    type_alert = models.CharField(
        max_length=300,
        choices=TYPE_ALERT_CHOICES,
        verbose_name="Tipo de alerta",
        blank=True,
        null=True,
    )

    type_notification = models.CharField(
        max_length=50,
        choices=TYPE_NOTIFICATION_CHOICES,
        verbose_name="Tipo de notificación",
    )

    start_date = models.DateField(blank=True, null=True, verbose_name="Fecha inicio")
    end_date = models.DateField(blank=True, null=True, verbose_name="Fecha fin")

    is_periodic = models.BooleanField(default=False, verbose_name="Cada registro")
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    is_read = models.BooleanField(default=False, verbose_name="Leido")
    is_response = models.BooleanField(default=False, verbose_name="Respuesta")
    is_wait = models.BooleanField(default=False, verbose_name="Espera")
    is_finish = models.BooleanField(default=False, verbose_name="Finalizado")

    class Meta:
        """Meta data notifications"""

        verbose_name = "Notificación"
        verbose_name_plural = "Notificaciones"

    def __str__(self):
        return f"{self.point_catchment}"


class ResponseNotificationsCatchment(ModelApi):
    """Response Notifications Model."""

    notification = models.ForeignKey(
        NotificationsCatchment,
        related_name="responses",
        on_delete=models.CASCADE,
        verbose_name="Notificación",
    )
    user = models.ForeignKey(
        User, related_name="responses", on_delete=models.CASCADE, verbose_name="Usuario"
    )
    response = models.CharField(max_length=1300, verbose_name="Respuesta")

    class Meta:
        """Meta data response notifications"""

        verbose_name = "Respuesta de notificación"
        verbose_name_plural = "Respuestas de notificaciones"

    def __str__(self):
        return f"{self.notification}"


class TypeFileCatchment(ModelApi):
    """Type File Model."""

    name = models.CharField(max_length=300, verbose_name="Nombre")
    internal = models.BooleanField(default=False, verbose_name="Interno")

    class Meta:
        """Meta data type file"""

        verbose_name = "Tipo de archivo"
        verbose_name_plural = "Tipos de archivos"

    def __str__(self):
        return f"{self.name}"


class FileCatchment(ModelApi):
    """File Model."""

    point_catchment = models.ForeignKey(
        CatchmentPoint,
        related_name="files",
        on_delete=models.CASCADE,
        verbose_name="Punto de captacion",
    )
    type_file = models.ForeignKey(
        TypeFileCatchment,
        related_name="files",
        on_delete=models.CASCADE,
        verbose_name="Tipo de archivo",
    )
    name = models.CharField(max_length=300, verbose_name="Nombre")
    file = models.FileField(upload_to="files_catchment", verbose_name="Archivo")
    description = models.CharField(
        max_length=300, verbose_name="Descripción", blank=True, null=True
    )
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        """Meta data file"""

        verbose_name = "Archivo"
        verbose_name_plural = "Archivos"

    def __str__(self):
        return f"{self.point_catchment}"


class ProfileDataConfigCatchment(ModelApi):
    """Data Configuration Profile."""

    point_catchment = models.ForeignKey(
        CatchmentPoint,
        related_name="data_config_profiles",
        on_delete=models.CASCADE,
        verbose_name="Punto de captacion",
        blank=True,
        null=True,
    )
    token_service = models.CharField(max_length=400, blank=True, null=True)
    d1 = models.DecimalField(
        default=0.0, verbose_name="Profundidad(mt)", max_digits=5, decimal_places=2
    )
    d2 = models.DecimalField(
        default=0.0,
        verbose_name="Posicionamiento de bomba(mt)",
        max_digits=5,
        decimal_places=2,
    )
    d3 = models.DecimalField(
        default=0.0,
        verbose_name="Posicionamiento nivel(mt)",
        max_digits=5,
        decimal_places=2,
    )
    d4 = models.DecimalField(
        default=0.0,
        verbose_name="Diametro ducto salida bomba(pulg)",
        max_digits=5,
        decimal_places=2,
    )
    d5 = models.DecimalField(
        default=0.0,
        verbose_name="Diametro flujometro(pulg)",
        max_digits=5,
        decimal_places=2,
    )
    d6 = models.IntegerField(
        default=0.0, verbose_name="Caudalimetro inicial", blank=True, null=True
    )
    is_telemetry = models.BooleanField(default=False, verbose_name="Activar telemetría")
    date_start_telemetry = models.DateField(
        blank=True, null=True, verbose_name="Fecha inicio telemetria"
    )
    date_delivery_act = models.DateField(
        blank=True, null=True, verbose_name="Fecha acta de entrega"
    )
    addition = models.IntegerField(
        default=0,
        verbose_name="Adicion (Reset)",
        help_text="Valor acumulado automáticamente cuando el sensor se reinicia (glitch/reset)."
    )

    class Meta:
        """Meta data profile data config"""

        verbose_name = "Configuracion de datos"
        verbose_name_plural = "Configuracion de datos"

    def __str__(self):
        return f"{self.point_catchment}"


class DgaDataConfigCatchment(ModelApi):
    """Data Configuration Profile DGA."""

    point_catchment = models.ForeignKey(
        CatchmentPoint,
        related_name="dga_data_config_profiles",
        on_delete=models.CASCADE,
        verbose_name="Punto de captacion",
    )

    standards_choices = [
        ("SIN_ESTANDAR", "sin estandar"),
        ("MAYOR", "mayor"),
        ("MEDIO", "medio"),
        ("MENOR", "menor"),
        ("CAUDALES_MUY_PEQUENOS", "cmp"),
    ]

    types_dga_choices = [
        ("SUBTERRANEO", "subterraneo"),
        ("SUPERFICIAL", "superficial"),
    ]

    send_dga = models.BooleanField(default=False, verbose_name="Activar cumplimiento")

    standard = models.CharField(
        max_length=300,
        default="SIN_ESTANDAR",
        choices=standards_choices,
        verbose_name="Estandar",
    )
    type_dga = models.CharField(
        max_length=300,
        blank=True,
        null=True,
        choices=types_dga_choices,
        default="SUBTERRANEO",
        verbose_name="Tipo",
    )
    code_dga = models.CharField(
        max_length=1200, blank=True, null=True, verbose_name="Codigo de obra(dga)"
    )
    flow_granted_dga = models.DecimalField(
        max_length=1200,
        default=0.0,
        verbose_name="Caudal otorgado(lt/s)",
        max_digits=5,
        decimal_places=2,
    )
    total_granted_dga = models.IntegerField(
        blank=True, null=True, verbose_name="Totalizado otorgado(m3)"
    )
    shac = models.CharField(
        max_length=1200, blank=True, null=True, verbose_name="Sector hidrologico(SHAC)"
    )
    region_dga = models.CharField(
        max_length=300, blank=True, null=True, verbose_name="DGA Región"
    )
    date_start_compliance = models.DateField(
        blank=True, null=True, verbose_name="Fecha inicio envío DGA"
    )
    date_created_code = models.DateField(
        blank=True, null=True, verbose_name="Fecha codigo creacion DGA"
    )
    name_informant = models.CharField(
        max_length=1200, default="Diego Mardones", verbose_name="Nombre informante"
    )
    rut_report_dga = models.CharField(
        max_length=1400, default="17352192-8", verbose_name="RUT"
    )
    password_dga_software = models.CharField(
        max_length=1400,
        default='',
        blank=True,
        verbose_name="clave DGA",
        help_text='Contraseña software DGA. Dejar vacío para usar default del sistema.'
    )

    class Meta:
        """Meta data profile data config"""

        verbose_name = "Configuracion de datos DGA"
        verbose_name_plural = "Configuraciones de datos DGA"

    def get_dga_password(self):
        """
        Obtener contraseña DGA.

        Retorna la contraseña personalizada del punto o la contraseña
        por defecto del sistema configurada en variables de entorno.

        Returns:
            str: Contraseña DGA a utilizar
        """
        from django.conf import settings
        return self.password_dga_software or settings.DGA_DEFAULT_PASSWORD

    def __str__(self):
        return f"{self.point_catchment}"


class SchemesCatchment(ModelApi):
    """Schemes Model."""

    points_catchment = models.ManyToManyField(
        CatchmentPoint,
        related_name="schemes",
        verbose_name="Punto de captacion",
        blank=True,
    )
    name = models.CharField(max_length=300, verbose_name="Nombre")
    description = models.CharField(max_length=300, verbose_name="Descripción")

    class Meta:
        """Meta data schemes"""

        verbose_name = "Esquema"
        verbose_name_plural = "Esquemas"

    def __str__(self):
        return f"{self.name}"


class Variable(ModelApi):
    """Variable Model."""

    scheme_catchment = models.ForeignKey(
        SchemesCatchment,
        related_name="variables",
        on_delete=models.CASCADE,
        verbose_name="Esquema",
    )

    PROVIDERS_CHOICES = [
        ("NOVUS", "novus"),
        ("NETTRA", "nettra"),
        ("TWIN", "twin"),
    ]
    VARIABLES_CHOICES = [
        ("NIVEL", "nivel"),
        ("CAUDAL", "caudal"),
        ("CAUDAL_PROMEDIO", "caudal_promedio((diff/3600)*1000)"),
        ("TOTALIZADO", "totalizado"),
    ]

    str_variable = models.CharField(max_length=400, verbose_name="Variable (str)")
    label = models.CharField(max_length=400, verbose_name="Etiqueta")

    type_variable = models.CharField(
        max_length=1200, choices=VARIABLES_CHOICES, verbose_name="Tipo variable"
    )

    token_service = models.CharField(
        max_length=400, blank=True, null=True, verbose_name="Token"
    )
    service = models.CharField(
        max_length=1200,
        choices=PROVIDERS_CHOICES,
        blank=True,
        null=True,
        verbose_name="Proveedor",
    )

    # Total
    pulses_factor = models.IntegerField(
        blank=True,
        null=True,
        default=1000,
        verbose_name="Pulsos(solo aplica a totalizadores (pulsos*pulsos_factor)/1000)",
    )


    # Caudal
    convert_to_lt = models.BooleanField(
        default=False, verbose_name="Pasar de m3 a lt(solo aplica en caudal) litros/3,6"
    )
    # Nivel
    calculate_nivel = models.IntegerField(
        blank=True, null=True, verbose_name="Base Calculo nivel(n/base calculo)"
    )

    class Meta:
        """Meta data variable"""

        verbose_name = "Variable"
        verbose_name_plural = "Variables"

    def __str__(self):
        return str(self.scheme_catchment)


class RegisterPersons(ModelApi):
    """Register Persons Model."""

    profile = models.ForeignKey(
        ProfileDataConfigCatchment, blank=True, null=True, on_delete=models.CASCADE
    )
    name = models.CharField(max_length=300, blank=True, null=True)
    email = models.CharField(max_length=300, blank=True, null=True)
    phone = models.CharField(max_length=300, blank=True, null=True)

    class Meta:
        """Meta data register persons"""

        verbose_name = "Persona registrada"
        verbose_name_plural = "Personas registradas"

    def __str__(self):
        return str(self.name)
