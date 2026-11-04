# Build context is infra/gateway/. nginx.conf is generated from routes.json.
FROM nginx:1.29.3-alpine
COPY nginx.conf /etc/nginx/nginx.conf
EXPOSE 8000
