# Build stage
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Serve stage
FROM nginx:alpine

# Copy nginx config (we will use the one from the root repo, mapped via docker-compose, or a standard one)
# actually, docker-compose maps ../nginx.conf to /etc/nginx/conf.d/default.conf
# so we just copy the build output to /usr/share/nginx/html where nginx looks.
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
