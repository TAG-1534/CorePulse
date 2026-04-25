FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN apk add --no-cache gcc musl-dev linux-headers python3-dev
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "app.py"]
