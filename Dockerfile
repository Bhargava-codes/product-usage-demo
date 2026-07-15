# Hugging Face Spaces (Docker SDK). Also a generic container image for the app.
# HF routes to app_port (7860 by default; set it in the Space README frontmatter).
FROM python:3.12-slim

# HF Spaces run the container as uid 1000 — create a matching user so the
# app can write the seeded CSVs.
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

COPY --chown=user backend/requirements.txt ./backend/requirements.txt
RUN pip install --user --no-cache-dir -r backend/requirements.txt

COPY --chown=user backend ./backend
COPY --chown=user frontend ./frontend

WORKDIR /app/backend
EXPOSE 7860

# Data CSVs are seeded automatically on startup (see app/api.py lifespan).
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "7860"]
