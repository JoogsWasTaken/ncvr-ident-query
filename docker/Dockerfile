FROM docker.io/postgres:16-alpine

RUN apk update --no-cache && \
    apk upgrade --no-cache && \
    apk add curl unzip --no-cache && \
    curl -o /tmp/ncvr.zip -sL "https://s3.amazonaws.com/dl.ncsbe.gov/data/ncvoter_Statewide.zip"