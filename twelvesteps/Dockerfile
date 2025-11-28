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
RUN echo '#!/bin/sh\n\
set -e\n\
echo "Waiting for database to be ready..."\n\
until pg_isready -h postgres -p 5432 -U postgres; do\n\
  echo "Database is unavailable - sleeping"\n\
  sleep 1\n\
done\n\
echo "Database is ready!"\n\
echo "Applying migrations..."\n\
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://postgres:password@postgres:5432/twelvesteps}"\n\
python apply_migrations_smart.py\n\
if [ $? -ne 0 ]; then\n\
  echo "Migration failed!"\n\
  exit 1\n\
fi\n\
echo "Migrations applied successfully!"\n\
echo "Starting API server..."\n\
exec python -m uvicorn api.main:app --host 0.0.0.0 --port 8000\n\
' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]

