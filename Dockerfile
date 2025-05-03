# 1) Builder stage
FROM python:3.13-alpine AS builder
WORKDIR /app
RUN apk add --no-cache build-base
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY relay /app

# 2) Runtime stage
FROM python:3.13-alpine
WORKDIR /app

# Copy Python packages and CLI scripts
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code and entrypoint
COPY --from=builder /app /app
COPY entrypoint.sh /app/entrypoint.sh

# Expose port
EXPOSE 25892

ENTRYPOINT ["/app/entrypoint.sh"]

# Allow for passing arguments to the entrypoint
CMD []
