FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 TZ=Europe/Moscow

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./
CMD ["python", "-u", "starter.py"]
