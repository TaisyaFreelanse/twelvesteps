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
echo "Checking DATABASE_URL..."\n\
if [ -z "$DATABASE_URL" ]; then\n\
  echo "Error: DATABASE_URL environment variable is not set"\n\
  exit 1\n\
fi\n\
echo "DATABASE_URL is set (host: $(echo $DATABASE_URL | sed -n "s/.*@\\([^:]*\\).*/\\1/p"))"\n\
echo "Applying migrations..."\n\
python apply_migrations_smart.py\n\
if [ $? -ne 0 ]; then\n\
  echo "Migration failed!"\n\
  exit 1\n\
fi\n\
echo "Migrations applied successfully!"\n\
echo "Starting API server..."\n\
exec python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}\n\
' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]

