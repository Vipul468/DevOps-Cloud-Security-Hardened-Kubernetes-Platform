FROM python:3.12-slim

# Security: create non-root user with fixed UID
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY app/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

RUN chown -R 1000:1000 /app

# Run container as non-root UID
USER 1000

EXPOSE 5000

CMD ["python", "app.py"]