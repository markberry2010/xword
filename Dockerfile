# Stage 1: Build frontend
FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Build Rust solver
FROM python:3.11-slim AS rust-build
RUN apt-get update && apt-get install -y curl build-essential && rm -rf /var/lib/apt/lists/*
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"
RUN pip install maturin

WORKDIR /app
COPY solver-rs/ ./solver-rs/
RUN cd solver-rs && maturin build --release --out /app/wheels

# Stage 3: Python runtime
FROM python:3.11-slim AS runtime
WORKDIR /app

# Install Python dependencies
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

# Install Rust solver wheel
COPY --from=rust-build /app/wheels/*.whl /tmp/
RUN pip install /tmp/*.whl && rm /tmp/*.whl

# Copy application code
COPY server/ ./server/
COPY data/ ./data/

# Copy built frontend from stage 1
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

ENV ENV=production
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
