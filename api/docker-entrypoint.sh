#!/bin/sh
# docker-entrypoint.sh

# Ensure dependencies are installed (safety net for cron container rebuilds)
pip install -q -r requirements.txt

# If this is going to be a cron container, set up the crontab.
if [ "$1" = cron ]; then
  ./manage.py crontab add
  ./manage.py crontab show
fi

# Launch the main container command passed as arguments.
echo "$@"
exec "$@"
