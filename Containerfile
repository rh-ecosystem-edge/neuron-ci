FROM registry.access.redhat.com/ubi9/ubi-minimal:latest
LABEL maintainer="rh-ecosystem-edge"

RUN microdnf install -y python3 python3-pip tar gzip jq make && \
    microdnf clean all

RUN curl -sL https://mirror.openshift.com/pub/openshift-v4/clients/ocp/stable/openshift-client-linux.tar.gz \
    | tar xzf - -C /usr/local/bin oc kubectl

COPY operators/ /app/operators/
COPY Makefile /app/Makefile
WORKDIR /app
