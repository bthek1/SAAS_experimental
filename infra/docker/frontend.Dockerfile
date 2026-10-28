FROM node:24-slim

ENV NODE_ENV=development

WORKDIR /app

COPY package.json package-lock.json* ./

RUN npm install

COPY . /app

EXPOSE 5174

CMD ["npm", "run", "dev", "--", "--host"]
