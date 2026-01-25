# Arquitectura de la API: Mapa Visual

Este diagrama ilustra la estructura actual de los endpoints en SmartHydro, destacando la unificación y la coexistencia con módulos legacy/especializados.

```mermaid
graph TD
    User([Cliente / Frontend]) --> Router{API Router}
    
    subgraph "Core Unified (V0)"
        Router -->|/api/points| Points[Catchment Points]
        Router -->|/api/devices| Devices[IoT Devices]
        Router -->|/api/dashboard| Dashboard[Dashboard Services]
        
        Points -->|Consumes| StatusService
        Devices -->|Consumes| StatusService
    end
    
    subgraph "Extended Services"
        Router -->|/api/console| DashExt[Advanced Dashboard]
        Router -->|/api/dynamic| DynamicEng[Dynamic Engine]
    end
    
    subgraph "Specialized Modules"
        Router -->|/api/crm| CRM[Client Relationship]
        Router -->|/api/chat-bot| Chat[LLM Agent]
        Router -->|/api/registry| Registry[Server-Driven UI]
        Router -->|/api/providers| Providers[Integrations]
    end
    
    subgraph "Infrastructure Layer"
        Points -.->|Relation| Devices
        Devices -.->|Config| Registry
    end
    
    style Router fill:#f9f,stroke:#333,stroke-width:2px
    style Points fill:#bbf,stroke:#333
    style Devices fill:#bbf,stroke:#333
    style Dashboard fill:#bbf,stroke:#333
    
    style DashExt fill:#eee,stroke:#999,stroke-dasharray: 5 5
    style DynamicEng fill:#eee,stroke:#999,stroke-dasharray: 5 5
```

## Leyenda
- **Core Unified (Azul)**: Endpoints modernos y centralizados.
- **Extended Services (Gris)**: Servicios avanzados de consola y motor dinámico.
- **Specialized Modules**: Apps independientes con dominios específicos.
