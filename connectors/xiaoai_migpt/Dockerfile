FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --omit=dev

COPY src ./src

ENV NODE_ENV=production
ENV NODE_OPTIONS=--max-old-space-size=128

CMD ["npm", "start"]
