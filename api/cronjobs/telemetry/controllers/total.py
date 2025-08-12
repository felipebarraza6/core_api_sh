"""Procesamiento de totalizados."""

from api.core.models import InteractionDetail


def total_m3(pulses_factor, value, point_catchment):
    """Calcular total en m3 usando la fórmula correcta: (pulsos * constante) / 1000"""
    try:
        # Validar que pulses_factor sea válido
        if not pulses_factor or pulses_factor <= 0:
            print(f"Error: pulses_factor no válido: {pulses_factor}, usando constante por defecto 1000")
            # Si la constante es 0 o inválida, asumir que ya viene en m3 (constante = 1000)
            pulses_factor = 1000

        # Obtener el último total registrado para este punto
        ultimo_registro = (
            InteractionDetail.objects.filter(catchment_point_id=point_catchment["id"])
            .exclude(total__isnull=True)
            .order_by("-created")
            .first()
        )

        if ultimo_registro:
            ultimo_total = float(ultimo_registro.total)
        else:
            ultimo_total = 0.0

        # FÓRMULA CORREGIDA: total = (pulsos * constante) / 1000
        nuevo_total = (float(value) * float(pulses_factor)) / 1000.0

        # Si el nuevo total es menor al anterior, sumarlo (caso de reset del contador)
        if nuevo_total < ultimo_total:
            print(
                f"Totalizador menor al anterior: {nuevo_total} < {ultimo_total}, sumando..."
            )
            total_final = ultimo_total + nuevo_total
        else:
            total_final = nuevo_total

        if total_final < 0 or abs(total_final) >= 1000000:
            print("Calculated value exceeds the allowed precision and scale")
            return 0.00
        return round(float(total_final), 2)
    except (ValueError, ZeroDivisionError) as e:
        print(f"Error: {e}")
        return 0.00


def total_hour(total, point_catchment):
    """Calcular diferencia entre las dos últimas mediciones (CORREGIDO)"""
    try:
        # Obtener los dos registros más recientes
        registros = (
            InteractionDetail.objects.filter(
                catchment_point_id=point_catchment["id"]
            )
            .exclude(total__isnull=True)
            .order_by("-created")[:2]
        )

        total_actual = float(total)

        if len(registros) >= 2:
            # CORRECCION: tomar el SEGUNDO registro (el anterior)
            total_anterior = float(registros[1].total)
            
            # Manejar caso de reset del contador
            if total_actual < total_anterior:
                diferencia = total_actual  # Usar el valor actual como diferencia
            else:
                diferencia = total_actual - total_anterior

            if diferencia < 0:
                diferencia = 0.0

            print(f"Calculo: {total_actual} - {total_anterior} = {diferencia}")
            return float(round(diferencia, 2))
            
        elif len(registros) == 1:
            # Solo hay un registro previo
            total_anterior = float(registros[0].total)
            diferencia = total_actual - total_anterior
            
            if diferencia < 0:
                diferencia = 0.0
                
            print(f"Calculo (1 prev): {total_actual} - {total_anterior} = {diferencia}")
            return float(round(diferencia, 2))
        else:
            # Primer registro del punto
            print(f"Primer registro: {total_actual}")
            return float(total_actual)
    except Exception as e:
        print(f"Error calculando diferencia entre mediciones: {e}")
        return 0.0


def total_day(total, point_catchment):
    """Calcular acumulado de todas las diferencias del día actual"""
    try:
        from datetime import datetime, time
        import pytz

        chile = pytz.timezone("America/Santiago")
        ahora = datetime.now(chile)
        
        # Inicio del día actual (medianoche)
        inicio_dia = datetime.combine(ahora.date(), time.min).replace(tzinfo=chile)

        # Primero calcular el total_diff actual (diferencia con el anterior)
        total_diff_actual = total_hour(total, point_catchment)

        # Obtener todos los registros del día actual (excluyendo el que se está calculando)
        registros_hoy = (
            InteractionDetail.objects.filter(
                catchment_point_id=point_catchment["id"],
                created__gte=inicio_dia
            )
            .exclude(total__isnull=True)
            .exclude(total_diff__isnull=True)
            .order_by("created")
        )

        # Sumar todos los total_diff del día actual
        suma_diferencias_hoy = float(sum(r.total_diff for r in registros_hoy))

        # Agregar la diferencia actual
        total_acumulado_dia = suma_diferencias_hoy + total_diff_actual

        if total_acumulado_dia < 0:
            total_acumulado_dia = 0.0

        # Asegurar que devuelve float, no string
        return float(round(total_acumulado_dia, 2))
    except Exception as e:
        print(f"Error calculando acumulado diario: {e}")
        return 0.0
