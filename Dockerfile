# PitWall app image. Build: docker build -t pitwall .   Run: docker run -p 8501:8501 pitwall
FROM python:3.13-slim-bookworm

# Pinned uv, installed from its own image; use the image's Python instead of downloading one
# (pyproject.toml asks for a uv-managed Python, which would add a download to every build).
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv
ENV UV_PYTHON_PREFERENCE=system UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_CACHE=1 \
    PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"

# Build as the unprivileged user from the start: a later chown -R would copy the whole virtualenv into a new layer.
RUN useradd --create-home app && mkdir /app && chown app /app
USER app
WORKDIR /app

# Dependencies first, so they stay cached until pyproject.toml or uv.lock change.
COPY --chown=app pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY --chown=app src ./src
COPY --chown=app app.py ./
COPY --chown=app .streamlit ./.streamlit
COPY --chown=app data/processed ./data/processed
RUN uv sync --frozen --no-dev && test -f data/processed/lap_dataset.parquet

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)"
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
