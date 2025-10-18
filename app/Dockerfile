FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl tini \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy the whole app dir (refresher package + cli.py)
COPY . /app/

ENTRYPOINT ["/usr/bin/tini","--"]
CMD ["python","-m","cli","run"]
