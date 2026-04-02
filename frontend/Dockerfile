# syntax=docker/dockerfile:1
# Stage 1: Build the React/Vite app
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

# Stage 2: Serve the static build on port 3001
FROM nginx:1.28-alpine AS runtime

# Remove default nginx config and replace with a minimal one for port 3001
RUN rm /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

RUN printf 'server {\n\
    listen 3001;\n\
    server_name _;\n\
    root /usr/share/nginx/html;\n\
    index index.html;\n\
    location / {\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
}\n' > /etc/nginx/conf.d/app.conf

EXPOSE 3001
CMD ["nginx", "-g", "daemon off;"]
