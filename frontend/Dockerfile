FROM node:24-alpine AS builder
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
# Vite는 VITE_*를 빌드 시점에 번들에 박는다 — ARG로 선언하지 않으면 --build-arg가 버려져 빈 값으로 빌드됐다
ARG VITE_SUPABASE_URL VITE_SUPABASE_ANON_KEY VITE_REDIRECT_URL VITE_SENTRY_DSN VITE_API_DOMAIN
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL \
    VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY \
    VITE_REDIRECT_URL=$VITE_REDIRECT_URL \
    VITE_SENTRY_DSN=$VITE_SENTRY_DSN \
    VITE_API_DOMAIN=$VITE_API_DOMAIN
RUN npm run build

FROM nginx:1.29-alpine AS runtime
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx/nginx.conf /etc/nginx/nginx.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
