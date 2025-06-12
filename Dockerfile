FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Default path where the database will be stored. Can be overridden at runtime.
ENV DATABASE_PATH=/data/duescord.db
VOLUME ["/data"]
CMD ["python", "bot.py"]
