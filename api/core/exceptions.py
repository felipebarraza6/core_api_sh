
def json_on_error_exception_handler(exc, context):
    """
    Wrapper del exception_handler de DRF que fuerza JSON para cualquier
    respuesta de error (status_code >= 400), evitando que los clientes que
    pidan XLSX reciban un archivo corrupto cuando en realidad hay un error.
    """
    from rest_framework.views import exception_handler
    from rest_framework.renderers import JSONRenderer
    
    response = exception_handler(exc, context)
    if response is not None:
        try:
            response.accepted_renderer = JSONRenderer()
            response.accepted_media_type = 'application/json'
            response['Content-Type'] = 'application/json'
        except Exception:
            # Si por algún motivo no se pueden ajustar los atributos, regresamos igual
            pass
    return response
