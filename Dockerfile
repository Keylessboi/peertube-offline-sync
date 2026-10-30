FROM python:3.12-slim
RUN useradd -u 10001 -m pos
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
USER 10001
CMD ["peertube-offline-sync"]
