FROM python:3.12-slim
# ORT_DISABLE_TELEMETRY: ONNX Runtime reports usage to Microsoft by default. The package sets
# this itself on import; it is repeated here so that any other process started in this image,
# a shell or a one-off script, inherits it too.
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 ORT_DISABLE_TELEMETRY=1
WORKDIR /srv

# The engine's three model files are inside its wheel, so this install is the last time the
# image needs a network. Nothing is fetched when the container runs.
COPY pyproject.toml ./
COPY narrator ./narrator
RUN pip install --no-cache-dir .

# It decodes images that came from third-party sites. No root, no volume and no way out is what
# a decoder bug would find here.
RUN useradd --system --no-create-home narrator
USER narrator

EXPOSE 8000
CMD ["uvicorn", "narrator.main:app", "--host", "0.0.0.0", "--port", "8000"]
