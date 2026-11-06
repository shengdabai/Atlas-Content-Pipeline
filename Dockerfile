FROM python:3.11-slim AS builder

WORKDIR /app

COPY . .

FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /app/scripts ./scripts
COPY --from=builder /app/schema ./schema
COPY --from=builder /app/tests ./tests

ENV PYTHONUNBUFFERED=1

HEALTHCHECK NONE

ENTRYPOINT ["python", "scripts/getnote_frontmatter_pipeline.py"]
CMD ["--help"]
