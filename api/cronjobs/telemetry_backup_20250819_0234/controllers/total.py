"""Procesamiento de totalizados."""

from api.core.models import InteractionDetail


def total_m3(pulses_factor, value, point_catchment):
    """Calcular total en m3 usando la fórmula correcta: (pulsos * constante) / 1000
    - Usa el último total válido cuando el nuevo cálculo sea inválido o excesivo
    - Evita NameError garantizando que ultimo_total siempre exista
    """
    try:
        # Validar pulses_factor
        if not pulses_factor or float(pulses_factor) <= 0:
            print(f"Error: pulses_factor no válido: {pulses_factor}, usando constante por defecto 1000")
            pulses_factor = 1000

        # Último registro con pulses/total para este punto
        ultimo_registro = (
            InteractionDetail.objects.filter(catchment_point_id=point_catchment["id"])\
            .exclude(pulses__isnull=True)\
            .order_by("-created")\
            .first()
        )

        # Asegurar variables de respaldo
        if ultimo_registro:
            try:
                ultimo_pulses = int(float(ultimo_registro.pulses)) if ultimo_registro.pulses not in (None, "") else 0
            except (ValueError, TypeError):
                ultimo_pulses = 0
            try:
                ultimo_total = float(ultimo_registro.total) if ultimo_registro.total not in (None, "") else 0.0
            except (ValueError, TypeError):
                ultimo_total = 0.0
        else:
            ultimo_pulses = 0
            ultimo_total = 0.0

        # Cálculo nuevo
        pulsos_actuales = int(float(value)) if value not in (None, "") else 0
        nuevo_total = (float(pulsos_actuales) * float(pulses_factor)) / 1000.0

        # Manejo de reset de contador (pulsos actuales < últimos pulsos)
        if pulsos_actuales < ultimo_pulses:
            print(f"Totalizador menor al anterior: {pulsos_actuales} < {ultimo_pulses}, sumando...")
            ultimo_total_recalc = (float(ultimo_pulses) * float(pulses_factor)) / 1000.0
            diferencia_reset = pulsos_actuales
            total_final = ultimo_total_recalc + (diferencia_reset * float(pulses_factor)) / 1000.0
        else:
            total_final = nuevo_total

        # Protecciones: nunca corromper el total
        if total_final < 0:
            print(f"🚨 TOTAL NEGATIVO DETECTADO: {total_final}")
            print(f"🔒 MANTENIENDO ÚLTIMO TOTAL CORRECTO: {ultimo_total}")
            return str(int(round(ultimo_total)))

        if abs(total_final) >= 1000000:  # umbral sanity-check
            print(f"🚨 TOTAL EXCESIVO DETECTADO: {total_final}")
            print(f"🔒 MANTENIENDO ÚLTIMO TOTAL CORRECTO: {ultimo_total}")
            return str(int(round(ultimo_total)))

        # Retornar entero en string (CharField)
        return str(int(round(total_final)))

    except (ValueError, ZeroDivisionError) as e:
        print(f"Error en total_m3: {e}")
        try:
            return str(int(round(ultimo_total)))  # usa respaldo si existe
        except Exception:
            return "0"


def total_hour(total, point_catchment):
    """Calcular diferencia entre las dos últimas mediciones (CORREGIDO)"""
    try:
        registros = (
            InteractionDetail.objects.filter(catchment_point_id=point_catchment["id"])\
            .exclude(pulses__isnull=True)\
            .order_by("-created")[:2]
        )

        total_actual = float(total if total not in (None, "") else 0)

        if len(registros) >= 2:
            total_anterior = float(registros[1].total if registros[1].total not in (None, "") else 0)
            if total_actual < total_anterior:
                diferencia = total_actual
            else:
                diferencia = total_actual - total_anterior
            if diferencia < 0:
                print(f"🚨 DIFERENCIA NEGATIVA DETECTADA: {diferencia}")
                print(f"🔒 CORRIGIENDO A 0")
                diferencia = 0
            print(f"Calculo: {total_actual} - {total_anterior} = {diferencia}")
            return int(round(diferencia))

        elif len(registros) == 1:
            total_anterior = float(registros[0].total if registros[0].total not in (None, "") else 0)
            diferencia = total_actual - total_anterior
            if diferencia < 0:
                print(f"🚨 DIFERENCIA NEGATIVA DETECTADA: {diferencia}")
                print(f"🔒 CORRIGIENDO A 0")
                diferencia = 0
            print(f"Calculo (1 prev): {total_actual} - {total_anterior} = {diferencia}")
            return int(round(diferencia))
        else:
            print(f"Primer registro: {total_actual}")
            return int(round(total_actual))
    except Exception as e:
        print(f"Error calculando diferencia entre mediciones: {e}")
        return 0


def total_day(total, point_catchment):
    """Calcular acumulado de todas las diferencias del día actual"""
    try:
        from datetime import datetime
        import pytz
        chile = pytz.timezone("America/Santiago")
        hoy = datetime.now(chile).date()

        diferencias_hoy = (
            InteractionDetail.objects.filter(
                catchment_point_id=point_catchment["id"], created__date=hoy
            )
            .exclude(total_diff__isnull=True)
            .values_list("total_diff", flat=True)
        )

        if diferencias_hoy:
            suma_diferencias = sum([diff for diff in diferencias_hoy if (diff or 0) > 0])
            print(f"Acumulado del día: {suma_diferencias}")
            return int(round(suma_diferencias))
        else:
            print(f"No hay diferencias hoy, usando total actual: {total}")
            return int(round(float(total if total not in (None, "") else 0)))

    except Exception as e:
        print(f"Error calculando acumulado del día: {e}")
        return int(round(float(total if total not in (None, "") else 0)))
