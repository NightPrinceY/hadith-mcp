# HadithMCPServer — canonical hadith text (Arabic + English), keyword search
# Vendored from https://github.com/ovehbe/hadith-mcp (GPL-3.0-only; see NOTICE/LICENSE)

ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e .

COPY data/ ./data/

# hadith_mcp has no custom port/host env vars of its own — FastMCP's own
# FASTMCP_PORT/FASTMCP_HOST control the bind address (unlike VALIDATOR_MCP_PORT/
# ISLAMIC_MCP_PORT, which those servers' own code reads directly). FASTMCP_HOST
# must be 0.0.0.0 here: FastMCP defaults to 127.0.0.1, which is unreachable
# through Docker's port mapping from outside the container.
ENV FASTMCP_HOST=0.0.0.0
ENV FASTMCP_PORT=3008
EXPOSE 3008

CMD ["python", "-m", "hadith_mcp", "--transport", "streamable-http", "--log-level", "INFO"]
