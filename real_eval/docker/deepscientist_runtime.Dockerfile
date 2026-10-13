# DeepScientist runtime image (F05).
#
# The upstream repository ships no Dockerfile, so this one is maintained here.
# It is a reconstruction: it records the base image and the system dependencies
# the evaluation runs needed, so the image can be rebuilt from this repository
# alone. The base is the same NVIDIA PyTorch base the other runtime Dockerfiles
# in this directory use.
#
FROM nvcr.io/nvidia/pytorch:25.11-py3

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      nodejs \
      npm \
      git \
      curl \
      ca-certificates \
      bash \
      openssh-client \
      build-essential \
      make \
      g++ \
      pkg-config \
      sqlite3 \
      poppler-utils \
      chktex \
    && rm -rf /var/lib/apt/lists/*

# The original build deliberately did NOT upgrade npm: the apt-provided Node is
# 18.19.1 and npm@11 requires Node >= 20.17 (report sec. 11). Installing the two
# globals is the whole point of this image -- `ds` and `codex` must resolve to
# container-local binaries, per report sec. 14.
RUN npm install -g @researai/deepscientist \
    && npm cache clean --force

# Use the codex that DeepScientist ships with, NOT the newest published one.
# DeepScientist 1.6.0 declares "@openai/codex": "^0.114.0" and bundles 0.114.0,
# but installing @openai/codex globally pulled 0.159.3 and won on PATH.  That
# mismatch broke its runner -- codex_core::tools::router logged
# "unsupported custom tool call: exec" and the startup hello probe failed, so
# the framework could not read its own staged contract documents.
# Point /usr/local/bin/codex at the bundled copy (report sec.14 requires the
# binary to live at /usr/local/bin/codex).
RUN ln -sf /usr/local/lib/node_modules/@researai/deepscientist/node_modules/@openai/codex/bin/codex.js \
      /usr/local/bin/codex \
    && command -v codex \
    && codex --version

# Deliberately no TeX: report sec. 12 records that the LaTeX runtime was absent
# in the original image (pdflatex unavailable), while chktex was present.

WORKDIR /workspace

CMD ["/bin/bash"]
