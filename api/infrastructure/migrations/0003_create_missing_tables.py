# Generated manually to fix infrastructure tables

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('infrastructure', '0002_alter_connection_table_alter_devicemodel_table_and_more'),
    ]

    operations = [
        # Crear tablas si no existen
        migrations.RunSQL(
            sql="""
            -- Tabla infrastructure_connection (renombrar desde core_mqttconnection si existe)
            DO $$
            BEGIN
                IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'core_mqttconnection') THEN
                    ALTER TABLE core_mqttconnection RENAME TO infrastructure_connection;
                END IF;
            END $$;
            
            -- Crear infrastructure_connection si no existe
            CREATE TABLE IF NOT EXISTS infrastructure_connection (
                id bigserial PRIMARY KEY,
                created timestamp with time zone NOT NULL DEFAULT NOW(),
                modified timestamp with time zone NOT NULL DEFAULT NOW(),
                connection_name varchar(100) NOT NULL,
                broker_host varchar(255) NOT NULL,
                broker_port integer NOT NULL DEFAULT 1883,
                username varchar(100) NOT NULL DEFAULT '',
                password varchar(255) NOT NULL DEFAULT '',
                client_id varchar(100) NOT NULL UNIQUE,
                status varchar(15) NOT NULL DEFAULT 'DISCONNECTED',
                is_active boolean NOT NULL DEFAULT true,
                manufacturer_id bigint NOT NULL REFERENCES infrastructure_manufacturer(id) ON DELETE CASCADE
            );
            
            -- Crear infrastructure_manufacturer (renombrar desde core_equipmentprovider si existe)
            DO $$
            BEGIN
                IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'core_equipmentprovider') THEN
                    ALTER TABLE core_equipmentprovider RENAME TO infrastructure_manufacturer;
                END IF;
            END $$;
            
            CREATE TABLE IF NOT EXISTS infrastructure_manufacturer (
                id bigserial PRIMARY KEY,
                created timestamp with time zone NOT NULL DEFAULT NOW(),
                modified timestamp with time zone NOT NULL DEFAULT NOW(),
                name varchar(100) NOT NULL UNIQUE,
                code varchar(20) NOT NULL UNIQUE,
                description text NOT NULL DEFAULT '',
                website varchar(200) NOT NULL DEFAULT '',
                contact_email varchar(254) NOT NULL DEFAULT '',
                contact_phone varchar(20) NOT NULL DEFAULT '',
                mqtt_broker_host varchar(255) NOT NULL DEFAULT '',
                mqtt_broker_port integer NOT NULL DEFAULT 1883,
                mqtt_username varchar(100) NOT NULL DEFAULT '',
                mqtt_password varchar(255) NOT NULL DEFAULT '',
                mqtt_use_tls boolean NOT NULL DEFAULT false,
                is_active boolean NOT NULL DEFAULT true,
                integration_status varchar(20) NOT NULL DEFAULT 'NOT_STARTED'
            );
            
            -- Crear infrastructure_devicemodel (renombrar desde core_equipmentmodel si existe)
            DO $$
            BEGIN
                IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'core_equipmentmodel') THEN
                    ALTER TABLE core_equipmentmodel RENAME TO infrastructure_devicemodel;
                END IF;
            END $$;
            
            CREATE TABLE IF NOT EXISTS infrastructure_devicemodel (
                id bigserial PRIMARY KEY,
                created timestamp with time zone NOT NULL DEFAULT NOW(),
                modified timestamp with time zone NOT NULL DEFAULT NOW(),
                model_name varchar(100) NOT NULL,
                model_code varchar(50) NOT NULL,
                description text NOT NULL DEFAULT '',
                is_active boolean NOT NULL DEFAULT true,
                manufacturer_id bigint NOT NULL REFERENCES infrastructure_manufacturer(id) ON DELETE CASCADE,
                UNIQUE(manufacturer_id, model_code)
            );
            """,
            reverse_sql=migrations.RunSQL.noop
        ),
    ]
