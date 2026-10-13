FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e . && pip install --no-cache-dir alembic

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

# A fresh named volume copies this directory's mode, which is the only way to
# get a cache two services running as PUID can both write without a root
# init step.
RUN mkdir -p /reader-cache && chmod 1777 /reader-cache

EXPOSE 8000
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
