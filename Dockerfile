FROM python:3.7-alpine
RUN apk add --no-cache git

COPY . /tact
WORKDIR /tact

# TODO: Git re-init is gross at best
#
# Could find a way to ***
RUN git init . && \
    git add . && \
    # git -c user.email="bain.william.a@gmail.com" -c user.name="CI" commit -m "CI build" && \
    python setup.py develop && \
    pip install tact

CMD ["python", "setup.py", "test"]
