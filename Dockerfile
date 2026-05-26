FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Install uv from the image
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

# Run the check once, then exit. Fly.io Machines restart it on schedule.
CMD ["uv", "run", "python", "main.py"]
