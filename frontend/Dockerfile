# Dev server with a proxy to the API. The browser talks to this origin only;
# VITE_API_BASE_URL stays empty so paths never hard-code a host.
FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

ENV API_PROXY_TARGET=http://host.docker.internal:8000
ENV VITE_API_BASE_URL=

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
