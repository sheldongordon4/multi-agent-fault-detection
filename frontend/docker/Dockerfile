# syntax=docker/dockerfile:1

ARG NODE_VERSION=22.17.1

FROM node:${NODE_VERSION}-alpine AS development

ENV NODE_ENV=development

RUN corepack enable && corepack prepare pnpm@11.0.9 --activate

WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml* .npmrc* ./

RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile

COPY . .

EXPOSE 5173

CMD ["pnpm","dev"]
