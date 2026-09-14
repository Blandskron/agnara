# syntax=docker/dockerfile:1.9

ARG PYTHON_IMAGE=python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6

FROM ${PYTHON_IMAGE} AS builder

ARG UV_VERSION=0.12.13
WORKDIR /build

RUN python -m pip install --no-cache-dir "uv==${UV_VERSION}"

COPY pyproject.toml uv.lock ./
COPY packages/ packages/

RUN uv build --all-packages --out-dir /dist \
    && uv export --frozen --all-packages --no-dev --no-editable \
        --no-hashes --no-emit-project --no-emit-workspace --format requirements.txt \
        --output-file /runtime-requirements.txt \
    && printf 'uvicorn==0.52.4\n' >> /runtime-requirements.txt

FROM ${PYTHON_IMAGE} AS runtime

ARG OCI_CREATED=unknown
ARG OCI_REVISION
ARG OCI_VERSION=0.0.0-dev

LABEL org.opencontainers.image.title="Agnara" \
      org.opencontainers.image.description="Executable Agnara HTTP reference runtime" \
      org.opencontainers.image.source="https://github.com/Blandskron/agnara" \
      org.opencontainers.image.url="https://github.com/Blandskron/agnara" \
      org.opencontainers.image.documentation="https://github.com/Blandskron/agnara/blob/develop/docs/CONTAINERS.md" \
      org.opencontainers.image.version="${OCI_VERSION}" \
      org.opencontainers.image.revision="${OCI_REVISION}" \
      org.opencontainers.image.created="${OCI_CREATED}" \
      org.opencontainers.image.licenses="Apache-2.0"

RUN groupadd --gid 10001 agnara \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin agnara

COPY --from=builder /runtime-requirements.txt /tmp/runtime-requirements.txt
COPY --from=builder /dist/ /tmp/dist/
RUN python -m pip install --no-cache-dir --requirement /tmp/runtime-requirements.txt \
    && python -m pip install --no-cache-dir --no-deps /tmp/dist/*.whl \
    && rm -rf /tmp/dist /tmp/runtime-requirements.txt \
    && python -m pip cache purge

WORKDIR /opt/agnara
COPY --chown=agnara:agnara examples/http_service.py app.py

USER agnara:agnara
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

ENTRYPOINT ["python", "-m", "uvicorn"]
CMD ["app:asgi", "--host", "0.0.0.0", "--port", "8000"]