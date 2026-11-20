# Builds the API image: Python 3.13 plus the pinned packages.
# This is a development image, so it also includes pytest.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /code

# Install packages first so Docker can reuse this layer when only code changes.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY pytest.ini start.sh ./
COPY app ./app

EXPOSE 8000

CMD ["sh", "start.sh"]