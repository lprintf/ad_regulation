FROM node:20-alpine AS build

WORKDIR /app

# Copy dependency files for better caching
COPY package.json pnpm-lock.yaml* package-lock.json* ./

# Install dependencies (support both npm and pnpm)
RUN if [ -f pnpm-lock.yaml ]; then \
        npm install -g pnpm && pnpm install; \
    else \
        npm install; \
    fi

# Copy configuration files
COPY tsconfig.json vite.config.ts index.html tailwind.config.js postcss.config.js ./

# Copy source code and assets
COPY public ./public
COPY src ./src

# Build argument for API base URL
ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

# Build application
RUN if [ -f pnpm-lock.yaml ]; then \
        pnpm run build; \
    else \
        npm run build; \
    fi

# Production stage with nginx
FROM nginx:1.27-alpine

# nginx 配置通过 docker-compose volume 挂载到 /etc/nginx/templates/default.conf.template
# 生产环境: nginx.conf.template → default.conf.template
# 开发环境: nginx.dev.conf.template → default.conf.template

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["/docker-entrypoint.sh", "nginx", "-g", "daemon off;"]
