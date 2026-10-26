FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=10000
COPY requirements-rest.txt ./
RUN python -m pip install --no-cache-dir -r requirements-rest.txt
COPY core.py edge_tts_bridge.py rest_api.py ./
USER 65532
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn rest_api:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]
