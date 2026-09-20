FROM python:3.12-slim

# Security: run as a non-root user.
RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

USER appuser

EXPOSE 5000

CMD ["python", "app.py"]
