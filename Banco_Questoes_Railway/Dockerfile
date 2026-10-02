FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=America/Sao_Paulo
WORKDIR /app
COPY requirements.txt requirements-railway.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements-railway.txt
COPY . .
EXPOSE 8080
CMD ["gunicorn", "--config", "gunicorn.conf.py", "wsgi:app"]
