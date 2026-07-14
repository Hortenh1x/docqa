# NEXT_PUBLIC_* values are baked into the bundle at BUILD time — pass them as build args.
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_DEMO_API_KEY
ARG NEXT_PUBLIC_DEMO_MODE=true
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_PUBLIC_DEMO_API_KEY=$NEXT_PUBLIC_DEMO_API_KEY \
    NEXT_PUBLIC_DEMO_MODE=$NEXT_PUBLIC_DEMO_MODE
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000
RUN adduser -D appuser
COPY --from=build --chown=appuser /app/.next/standalone ./
COPY --from=build --chown=appuser /app/.next/static ./.next/static
USER appuser
EXPOSE 3000
CMD ["node", "server.js"]
