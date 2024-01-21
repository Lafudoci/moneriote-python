FROM python:3.10.13-slim
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt --no-cache-dir
CMD ["python", "moneriote.py"]