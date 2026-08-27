FROM python:3.12-slim-bookworm

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Groww's login page has no public API — the one-time (per session) login flow drives a
# real headless Chromium through it, so the runtime image needs an actual browser + its
# OS-level deps (fonts, codecs, etc.), not just the Python playwright package.
RUN playwright install --with-deps chromium

COPY . .

ENV PORT=4000
ENV TZ=Asia/Kolkata
EXPOSE 4000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
