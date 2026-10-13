ARG BASE_IMAGE=evoscientist:runtime-ready
FROM ${BASE_IMAGE}

USER root
WORKDIR /src

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock README.md ./
COPY EvoScientist ./EvoScientist

RUN uv sync --frozen --no-dev --no-editable --extra all-channels
RUN uv pip install --python /opt/venv/bin/python \
    numpy==2.4.5 \
    pandas==3.0.3 \
    scikit-learn==1.8.0

USER evosci
WORKDIR /workspace

LABEL org.opencontainers.image.source="https://github.com/EvoScientist/EvoScientist" \
      org.opencontainers.image.revision="f81a8b086ef9464bbcb74013ebbcf66cb1954b68" \
      org.opencontainers.image.description="EvoScientist upstream refresh for PsyDefDetect Kimi evaluation"
