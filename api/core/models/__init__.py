"""Models package."""

from .catchment_points import (
    CatchmentPoint,
    Client,
    DgaDataConfigCatchment,
    FileCatchment,
    NotificationsCatchment,
    ProfileDataConfigCatchment,
    ProfileIkoluCatchment,
    ProjectCatchments,
    RegisterPersons,
    ResponseNotificationsCatchment,
    TypeFileCatchment,
)
from .constants_system import (
    ConstantApplication,
    ConstantDefinition,
    DataCorrectionLog,
    ProviderDataSync,
)
from .enhanced_data_models import (
    DataAggregation,
    DataPoint,
    DataQualityMetric,
    DataStream,
    SupportTicket,
    TicketComment,
    TicketSLA,
    VariableDefinition,
)
from .management_super import (
    AlertRule,
    DeviceMaintenanceSchedule,
    EquipmentModel,
    EquipmentProvider,
    IoTDevice,
    MQTTConnection,
    MQTTMessageLog,
    SystemConfiguration,
    SystemMetrics,
)
from .telemetry import (
    TelemetryRecord,
    TelemetryScheme,
    SchemeVariable,
    CoreVariable,
    VirtualVariable,
)
from .users import User
from .utils import ModelApi
