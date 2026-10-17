FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . ./
RUN npm run build

FROM caddy:2-alpine
ENV PORT=3000 BACKEND_UPSTREAM=backend:8000
WORKDIR /srv
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=builder /app/dist ./
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD wget -q -O /dev/null "http://127.0.0.1:${PORT}/health" || exit 1
