# Built on nuc3 by roles/ai_apps in moolab2 (a pinned commit; the base image's
# digest is forced from outside with `podman build --from`).
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/

# uv, not pip: --frozen installs exactly the locked set the tests were green
# against. `pip install .` read only pyproject.toml, so a rebuild months later
# resolved whatever PyPI had that day (mcp 2.x broke the server on 2026-09-10;
# moolab2 LAB-71). --no-editable ships synology_mcp into site-packages;
# --inexact leaves pip/uv themselves alone.
RUN pip install --no-cache-dir uv \
    && UV_PROJECT_ENVIRONMENT=/usr/local uv sync --frozen --no-dev --no-editable --inexact \
    && pip uninstall -y uv

# Non-root user
RUN useradd --uid 1001 --no-create-home appuser
USER 1001

EXPOSE 8000

ENTRYPOINT ["python", "-m", "synology_mcp"]
