FROM python:3.11-slim

WORKDIR /app

COPY . .

ENV TZ=Europe/Kyiv
RUN apt-get update && apt-get install -y tzdata cron && rm -rf /var/lib/apt/lists/*

CMD ["python", "-m", "bot.bot"]
