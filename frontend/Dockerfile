FROM node:20-alpine AS build

WORKDIR /app

ARG VITE_REFUND_UAT_SIMULATOR=false
ENV VITE_REFUND_UAT_SIMULATOR=${VITE_REFUND_UAT_SIMULATOR}

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS production

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
