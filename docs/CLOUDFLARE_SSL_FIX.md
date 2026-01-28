# Solución Error 525 - Cambiar Modo SSL en Cloudflare

## Paso a Paso

1. **Ir a Cloudflare Dashboard**
   - Entrar a https://dash.cloudflare.com
   - Seleccionar dominio: smarthydro.app

2. **Ir a SSL/TLS Settings**
   - Menú lateral: SSL/TLS
   - Pestaña: Overview

3. **Cambiar modo SSL** (según tu cPanel)

   **Modo actual (probablemente):** Full (strict) o Full
   
   **Opciones:**
   
   ### A. Si cPanel NO tiene SSL:
   ```
   Cambiar a: Flexible
   ```
   - Cloudflare → Usuario: HTTPS (seguro)
   - Cloudflare → Servidor: HTTP (no seguro)
   - ✅ Soluciona error 525
   - ⚠️ Conexión Cloudflare-servidor no cifrada
   
   ### B. Si cPanel tiene SSL auto-firmado:
   ```
   Cambiar a: Full
   ```
   - Cloudflare → Usuario: HTTPS
   - Cloudflare → Servidor: HTTPS (acepta certificados auto-firmados)
   - ✅ Soluciona error 525
   - ✅ Mejor que Flexible
   
   ### C. Si cPanel tiene SSL válido (Let's Encrypt, etc):
   ```
   Mantener: Full (strict)
   ```
   - Verifica que el certificado no esté vencido
   - Verifica que el dominio coincida

4. **Esperar 1-5 minutos**
   - Los cambios pueden tardar en propagarse

5. **Verificar**
   ```bash
   curl -I https://smarthydro.app/
   ```
   - Debe mostrar HTTP/2 200 (o 404 si no hay index, pero sin error 525)

## Recomendación

**Si no necesitas página web en smarthydro.app:**
→ Dejar así, el error no afecta emails ni subdominios

**Si quieres que funcione sin configurar SSL en cPanel:**
→ Cambiar a modo "Flexible"

**Si tienes acceso al cPanel y tiempo:**
→ Instalar Let's Encrypt SSL en cPanel y usar modo "Full (strict)"
