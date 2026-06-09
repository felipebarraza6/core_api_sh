"""Custom authentication classes for SmartHydro API."""

from rest_framework.authentication import TokenAuthentication, get_authorization_header


class BearerTokenAuthentication(TokenAuthentication):
    """
    Acepta tanto 'Bearer <token>' como 'Token <token>'.

    El login legacy devuelve 'Authorization: Bearer <token>' en el header,
    por lo que muchos frontends usan ese prefijo. Esta clase permite que
    ambos formatos funcionen sin romper la compatibilidad existente.
    """
    keyword = "Bearer"

    def authenticate(self, request):
        # Intentar con Bearer primero
        result = super().authenticate(request)
        if result is not None:
            return result

        # Fallback a Token
        auth_header = get_authorization_header(request).split()
        if len(auth_header) == 2 and auth_header[0].lower() == b'token':
            return self.authenticate_credentials(auth_header[1].decode('utf-8'))

        return None
