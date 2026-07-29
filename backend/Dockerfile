FROM python:3.12-slim-bookworm

# System deps: ffmpeg for rendering, playwright deps for the Browser Engine
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    imagemagick \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libnss3 \
    libatk-bridge2.0-0 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*
RUN sed -i 's/rights="none" pattern="@\*"/rights="read|write" pattern="@*"/' /etc/ImageMagick-6/policy.xml || true
RUN sed -i '/<policy domain="path" rights="none" pattern="@\*"\/>/d' /etc/ImageMagick-6/policy.xml || true

WORKDIR /app

# Bundle Konva locally so scene recordings never depend on a live CDN
# fetch at render time — network latency there was causing a visible
# black flash before each scene's first paint.
RUN mkdir -p /app/vendor && wget -q https://unpkg.com/konva@9/konva.min.js -O /app/vendor/konva.min.js

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
