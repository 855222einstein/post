# ── Build stage ────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install dependencies into a local prefix so they're easy to copy
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Runtime stage ──────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy bot source
COPY bot/ ./bot/
COPY requirements.txt .

# Non-root user for security
RUN useradd -m botuser && chown -R botuser:botuser /app
USER botuser

# Telegram bot runs as a long-polling background worker — no port needed
CMD ["python", "-m", "bot.main"]
