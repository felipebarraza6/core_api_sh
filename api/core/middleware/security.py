class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)


        
        # Content-Security-Policy
        if 'Content-Security-Policy' not in response:
            # POLICY PERMISIVA (Solo para Admin interno, excluyendo login)
            if request.path.startswith('/admin/') and request.path != '/admin/login/':
                 response['Content-Security-Policy'] = (
                    "default-src 'self' http: https: data: blob: 'unsafe-inline' 'unsafe-eval'; "
                    "frame-ancestors 'self'; "
                    "base-uri 'self';"
                )
            # POLICY STRICT (Por defecto: Login, Home, 404s, Static Files, etc.)
            else:
                response['Content-Security-Policy'] = (
                    "default-src 'self' http: https: data: blob:; "
                    "frame-ancestors 'self'; "
                    "base-uri 'self';"
                )
            
        # Referrer-Policy
        if 'Referrer-Policy' not in response:
            response['Referrer-Policy'] = "strict-origin-when-cross-origin"
            
        # X-Content-Type-Options
        if 'X-Content-Type-Options' not in response:
            response['X-Content-Type-Options'] = "nosniff"
            
        # X-Frame-Options (Ya manejado por Django, pero reforzamos si falta)
        if 'X-Frame-Options' not in response:
            response['X-Frame-Options'] = "SAMEORIGIN"
            
        # Ocultar Banner del Servidor (Security through obscurity)
        # Evita que escaneres reporten "Default server banners displayed"
        response['Server'] = "SmartHydro Secure"
            
        return response
