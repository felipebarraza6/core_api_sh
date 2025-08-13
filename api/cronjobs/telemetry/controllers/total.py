"""Procesamiento de totalizados."""

from api.core.models import InteractionDetail


def total_m3(pulses_factor, value, point_catchment):
    """Calcular total en m3 usando la fórmula correcta: (pulsos * constante) / 1000"""
    try:
        # Validar que pulses_factor sea válido
        if not pulses_factor or pulses_factor <= 0:
            print(
                f"Error: pulses_factor no válido: {pulses_factor}, usando constante por defecto 1000"
            )
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
            # Convertir a entero si es string
            try:
                ultimo_total = int(float(ultimo_registro.total))
            except (ValueError, TypeError):
                ultimo_total = 0
        else:
            ultimo_total = 0

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

        # ✅ PROTECCIÓN MEJORADA: NUNCA EMBARRAR EL TOTAL
        if total_final < 0:
            print(f"🚨 TOTAL NEGATIVO DETECTADO: {total_final}")
            print(f"🔒 MANTENIENDO ÚLTIMO TOTAL CORRECTO: {ultimo_total}")
            return str(ultimo_total)  # ✅ MANTIENE EL TOTAL ANTERIOR CORRECTO

        # Solo validar valor excesivo (pero nunca negativo)
        if abs(total_final) >= 1000000:
            print(f"🚨 TOTAL EXCESIVO DETECTADO: {total_final}")
            print(f"🔒 MANTENIENDO ÚLTIMO TOTAL CORRECTO: {ultimo_total}")
            return str(ultimo_total)  # ✅ MANTIENE EL TOTAL ANTERIOR CORRECTO

        # ✅ RETORNAR COMO ENTERO EN STRING (para CharField)
        return str(int(round(total_final)))
    except (ValueError, ZeroDivisionError) as e:
        print(f"Error: {e}")
        # ✅ EN CASO DE ERROR, MANTENER ÚLTIMO TOTAL CORRECTO
        if ultimo_registro:
            print(f"🔒 ERROR EN CÁLCULO, MANTENIENDO ÚLTIMO TOTAL: {ultimo_total}")
            return str(ultimo_total)
        else:
            print("🔒 ERROR EN CÁLCULO Y NO HAY TOTAL PREVIO, USANDO 0")
            return "0"


def total_hour(total, point_catchment):
    """Calcular diferencia entre las dos últimas mediciones (CORREGIDO)"""
    try:
        # Obtener los dos registros más recientes
        registros = (
            InteractionDetail.objects.filter(catchment_point_id=point_catchment["id"])
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

            # ✅ PROTECCIÓN: NUNCA DIFERENCIAS NEGATIVAS
            if diferencia < 0:
                print(f"🚨 DIFERENCIA NEGATIVA DETECTADA: {diferencia}")
                print(f"🔒 CORRIGIENDO A 0")
                diferencia = 0

            print(f"Calculo: {total_actual} - {total_anterior} = {diferencia}")
            # ✅ RETORNAR COMO ENTERO
            return int(round(diferencia))

        elif len(registros) == 1:
            # Solo hay un registro previo
            total_anterior = float(registros[0].total)
            diferencia = total_actual - total_anterior

            # ✅ PROTECCIÓN: NUNCA DIFERENCIAS NEGATIVAS
            if diferencia < 0:
                print(f"🚨 DIFERENCIA NEGATIVA DETECTADA: {diferencia}")
                print(f"🔒 CORRIGIENDO A 0")
                diferencia = 0

            print(f"Calculo (1 prev): {total_actual} - {total_anterior} = {diferencia}")
            # ✅ RETORNAR COMO ENTERO
            return int(round(diferencia))
        else:
            # Primer registro del punto
            print(f"Primer registro: {total_actual}")
            # ✅ RETORNAR COMO ENTERO
            return int(round(total_actual))
    except Exception as e:
        print(f"Error calculando diferencia entre mediciones: {e}")
        return 0


def total_day(total, point_catchment):
    """Calcular acumulado de todas las diferencias del día actual"""
    try:
        # Obtener la fecha actual
        from datetime import datetime

        import pytz

        chile = pytz.timezone("America/Santiago")
        hoy = datetime.now(chile).date()

        # Obtener todas las diferencias del día actual
        diferencias_hoy = (
            InteractionDetail.objects.filter(
                catchment_point_id=point_catchment["id"], created__date=hoy
            )
            .exclude(total_diff__isnull=True)
            .values_list("total_diff", flat=True)
        )

        if diferencias_hoy:
            # ✅ SUMAR SOLO DIFERENCIAS POSITIVAS
            suma_diferencias = sum([diff for diff in diferencias_hoy if diff > 0])
            print(f"Acumulado del día: {suma_diferencias}")
            # ✅ RETORNAR COMO ENTERO
            return int(round(suma_diferencias))
        else:
            # Si no hay diferencias hoy, usar el total actual
            print(f"No hay diferencias hoy, usando total actual: {total}")
            # ✅ RETORNAR COMO ENTERO
            return int(round(float(total)))

    except Exception as e:
        print(f"Error calculando acumulado del día: {e}")
        # ✅ EN CASO DE ERROR, USAR TOTAL ACTUAL COMO ENTERO
        return int(round(float(total)))
