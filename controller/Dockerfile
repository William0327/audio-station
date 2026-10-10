FROM python:3.12.9-slim-bookworm
WORKDIR /app
COPY controller/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home controller
COPY controller /app/controller
COPY deploy /app/deploy
USER 10001:0
CMD ["uvicorn", "controller.app:app", "--host", "0.0.0.0", "--port", "8080"]
