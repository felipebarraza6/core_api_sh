FROM python:3.11

RUN mkdir /app
WORKDIR /app

ADD api/requirements.txt /app/
RUN pip install -r requirements.txt

RUN apt-get update
RUN apt-get install -y \
    gettext \
    nginx \
    vim \
    cron && touch /var/log/cron.log

RUN echo "daemon off;" >> /etc/nginx/nginx.conf
# ✅ FIX: Modificar nginx.conf para usar logs en /app/logs/nginx
RUN sed -i 's|error_log /var/log/nginx/error.log;|error_log /app/logs/nginx/error.log;|g' /etc/nginx/nginx.conf
RUN sed -i 's|access_log /var/log/nginx/access.log;|access_log /app/logs/nginx/access.log;|g' /etc/nginx/nginx.conf
RUN rm /etc/nginx/sites-enabled/default
RUN ln -s /app/conf/nginx-app.conf /etc/nginx/sites-enabled/

ADD . /app/

ENTRYPOINT ["./docker-entrypoint.sh"]
# ✅ OPTIMIZACIÓN: Usar Gunicorn en lugar de runserver para mejor rendimiento
# Gunicorn corre en puerto 8000, Nginx hace proxy desde puerto 80
CMD ["gunicorn", "--config", "gunicorn_config.py", "--bind", "0.0.0.0:8000", "api.wsgi:application"]

# Create directories for logs and static files
RUN mkdir -p /tmp/smarthydro
RUN touch /tmp/smarthydro/django.log
RUN chmod 755 /tmp/smarthydro
RUN chmod 644 /tmp/smarthydro/django.log

# Create static directory and give it proper permissions
RUN mkdir -p /app/staticfiles
RUN chmod 755 /app/staticfiles

# Create media directory
RUN mkdir -p /app/media
RUN chmod 755 /app/media

# Create logs directory
RUN mkdir -p /app/logs
RUN chmod 755 /app/logs

# Agregar entrypoint personalizado para cron
COPY cron-entrypoint.sh /usr/local/bin/cron-entrypoint.sh
RUN chmod +x /usr/local/bin/cron-entrypoint.sh

# Agregar script de rotación de logs
COPY rotate-cron-logs.sh /usr/local/bin/rotate-cron-logs.sh
RUN chmod +x /usr/local/bin/rotate-cron-logs.sh
