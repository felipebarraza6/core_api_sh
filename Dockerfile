FROM python:3

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
RUN rm /etc/nginx/sites-enabled/default
RUN ln -s /app/conf/nginx-app.conf /etc/nginx/sites-enabled/

ADD . /app/

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["python3", "./manage.py", "runserver", "0.0.0.0:80"]

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
