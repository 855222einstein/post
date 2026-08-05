FROM python:3.11-slim

# Don't write .pyc files; send logs straight to stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (Docker cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create the data directory for the SQLite database
RUN mkdir -p data

CMD ["python", "-m", "bot.main"]
