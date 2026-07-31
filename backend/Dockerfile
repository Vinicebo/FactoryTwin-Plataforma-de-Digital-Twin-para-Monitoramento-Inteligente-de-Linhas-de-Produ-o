FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# As dependências vêm primeiro para aproveitar o cache de camadas do Docker:
# mudar o código-fonte não força reinstalar tudo.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY pytest.ini ruff.toml ./
COPY tests ./tests

# Usuário sem privilégios.
RUN useradd --create-home --uid 1000 factorytwin \
    && mkdir -p /app/app/ml/artifacts \
    && chown -R factorytwin:factorytwin /app
USER factorytwin

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
