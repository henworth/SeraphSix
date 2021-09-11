FROM python:3.9-slim-buster

WORKDIR /usr/src/app

COPY seraphsix requirements.txt ./

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git; \
    pip install --no-cache-dir -r requirements.txt; \
    apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false; \
    rm -rf /var/lib/apt/lists/*

COPY arq_worker.py ./

CMD ["python", "./arq_worker.py"]
