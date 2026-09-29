# C1 Â· frontend
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# ---- development: Vite dev server with hot reload (source is bind-mounted)
FROM deps AS dev
ENV CHOKIDAR_USEPOLLING=true
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev"]

# ---- build
FROM deps AS build
# Vite inlines these at build time. Only public values belong here — the anon key ships in the
# bundle by design; never pass a service key or any other secret as a build arg.
ARG VITE_API_URL=/api
ARG VITE_AUTH_MODE=dev
ARG VITE_SUPABASE_URL=
ARG VITE_SUPABASE_ANON_KEY=
ENV VITE_API_URL=$VITE_API_URL     VITE_AUTH_MODE=$VITE_AUTH_MODE     VITE_SUPABASE_URL=$VITE_SUPABASE_URL     VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY
COPY . .
RUN npm run build

# ---- production: static files behind nginx
FROM nginx:1.27-alpine AS prod
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
