# Build stage
FROM node:20-alpine AS build

WORKDIR /app
COPY package.json ./
RUN npm install --frozen-lockfile

COPY . .
RUN npm run build

# Production stage – serve with nginx
FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html

# nginx config: redirect all routes to index.html (SPA fallback)
RUN printf 'server {\n\
    listen 80;\n\
    root /usr/share/nginx/html;\n\
    index index.html;\n\
    location / {\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
}' > /etc/nginx/conf.d/default.conf

EXPOSE 80
