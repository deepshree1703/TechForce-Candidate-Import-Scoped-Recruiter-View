# Runs the Vite dev server for the recruiting page.
# Dependencies are installed into the image; the source files are mounted by docker-compose.yml.
FROM node:24-alpine

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]