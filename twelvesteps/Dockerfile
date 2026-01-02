FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Create entrypoint script for migrations and server start
RUN cat > /app/entrypoint.sh << 'EOF'
#!/bin/sh
set -e
echo "Checking DATABASE_URL..."
if [ -z "$DATABASE_URL" ]; then
  echo "Error: DATABASE_URL environment variable is not set"
  exit 1
fi
echo "DATABASE_URL is set"
echo "Applying migrations..."
python apply_migrations_smart.py
if [ $? -ne 0 ]; then
  echo "Migration failed!"
  exit 1
fi
echo "Migrations applied successfully!"
echo "Starting API server..."
exec python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}
EOF
RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]

