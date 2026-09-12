FROM python:3.12-slim
WORKDIR /app
COPY nettest_canary.py .
CMD ["python","nettest_canary.py"]
