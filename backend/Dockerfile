# Build context: the repository root (the app reads database/migrations and ml/ from there).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 FLASK_APP=run.py
# libgomp1: OpenMP runtime used by XGBoost and scikit-learn
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ /app/backend/
COPY database/ /app/database/
COPY ml/ /app/ml/

# Train the ML models into the image (~2 min); --build-arg TRAIN_MODELS=false skips it and the
# app falls back to baseline forecasting and rule-only categorization.
ARG TRAIN_MODELS=true
RUN if [ "$TRAIN_MODELS" = "true" ]; then \
      APP_ENV=development DATABASE_URL=sqlite:// flask ml train; \
    fi

RUN useradd --create-home fintwin && chown -R fintwin /app
USER fintwin

EXPOSE 5000
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/health')"
ENTRYPOINT ["sh", "/app/backend/docker-entrypoint.sh"]
