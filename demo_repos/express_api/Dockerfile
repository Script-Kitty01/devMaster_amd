FROM node:18-alpine
WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
# SECURITY: Running as root
EXPOSE 3000
CMD ["node", "server.js"]
