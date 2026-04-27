FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install basic system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
RUN pip install uv

# Copy project specification files
COPY pyproject.toml uv.lock ./

# Copy the application source
COPY src/ ./src/
COPY README.md ./

# Install project dependencies system-wide (since we are inside a container)
RUN uv pip install --system -e .

# Create directory for file uploads
RUN mkdir -p uploads

# Expose API/UI port
EXPOSE 8000

# Start the application using the entrypoint script
CMD ["uv", "run", "screening-api"]
