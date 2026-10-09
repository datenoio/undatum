# undatum container image.
#
#   docker build -t undatum .                                  # core install
#   docker build -t undatum:full --build-arg EXTRAS=full .     # with the common extras
#   docker run --rm -v "$PWD:/data" undatum convert data.csv data.parquet
#
# The release workflow builds both variants and publishes them to
# ghcr.io/datenoio/undatum:<version> and ghcr.io/datenoio/undatum:<version>-full.

ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim AS build
# "full" installs the extras that need no system libraries beyond the slim image.
ARG EXTRAS=""
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY undatum ./undatum
RUN python -m venv /opt/undatum \
    && if [ "$EXTRAS" = "full" ]; then \
         spec=".[api,web,mcp,cloud,postgres,mysql,clickhouse,elastic,phone,plot,frictionless,tui]"; \
       elif [ -n "$EXTRAS" ]; then spec=".[${EXTRAS}]"; else spec="."; fi \
    && /opt/undatum/bin/pip install "$spec"

FROM python:${PYTHON_VERSION}-slim
LABEL org.opencontainers.image.title="undatum" \
      org.opencontainers.image.description="Convert, inspect, validate and transform data files" \
      org.opencontainers.image.source="https://github.com/datenoio/undatum" \
      org.opencontainers.image.licenses="MIT"
COPY --from=build /opt/undatum /opt/undatum
RUN useradd --create-home --uid 1000 undatum
ENV PATH="/opt/undatum/bin:$PATH" PYTHONUNBUFFERED=1
USER undatum
WORKDIR /data
ENTRYPOINT ["undatum"]
CMD ["--help"]
