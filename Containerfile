FROM python:3.12-slim

# Install the application
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir .

# Non-root user
RUN useradd --uid 1001 --no-create-home appuser
USER 1001

EXPOSE 8000

ENTRYPOINT ["python", "-m", "synology_mcp"]
