FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/manny
COPY pyproject.toml README.md ./
COPY apps/core ./apps/core
COPY configs ./configs
RUN python -m pip install --no-cache-dir .

USER nobody
EXPOSE 8765
CMD ["python", "-m", "uvicorn", "manny.main:app", "--app-dir", "apps/core", "--host", "127.0.0.1", "--port", "8765", "--no-access-log"]
