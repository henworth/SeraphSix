FROM python:3.9-slim-buster

WORKDIR /usr/src/app

COPY seraphsix ./seraphsix/
COPY requirements.txt ./

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git; \
    pip install --no-cache-dir -r requirements.txt; \
    apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends build-essential; \
    pip install --no-cache-dir meinheld gunicorn; \
    apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false build-essential; \
    rm -rf /var/lib/apt/lists/*

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

COPY docker/start.sh /start.sh
RUN chmod +x /start.sh

COPY docker/gunicorn_conf.py ./gunicorn_conf.py

COPY oauth_proxy.py ./

ENV PYTHONPATH=/usr/src/app

EXPOSE 80

ENTRYPOINT ["/entrypoint.sh"]

# Run the start script, it will check for an /app/prestart.sh script (e.g. for migrations)
# And then will start Gunicorn with Meinheld
CMD ["/start.sh"]
