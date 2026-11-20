FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /data

ENV DB_PATH=/data/bot.db
ENV PORT=8080

CMD ["python", "bot.py"]
