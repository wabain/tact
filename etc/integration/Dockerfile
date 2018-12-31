FROM python:3.7-alpine
RUN apk add --no-cache gcc musl-dev

COPY ./dist /dist
WORKDIR /srv

RUN pip install /dist/tact-*.tar.gz && pip install tact[server]

# It would be nice to be able to do the build in a separate stage instead,
# but figuring out what to copy across is tricky, so this will have to be
# good enough
RUN apk del gcc musl-dev

CMD ["tact", "serve"]
