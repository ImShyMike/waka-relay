# 1) Builder stage
FROM python:3.13-alpine AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY wakarelay /app

# 2) Runtime stage
FROM python:3.13-alpine
WORKDIR /app

# Copy Python packages and CLI scripts
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code and entrypoint
COPY --from=builder /app /app

# Expose port
EXPOSE 25892

ENTRYPOINT ["python", "main.py"]

# Allow for passing arguments to the entrypoint
CMD []
