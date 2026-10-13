# AutoResearchClaw opencode runtime (F04).
#
# Some AutoResearchClaw wrappers run the framework through the opencode CLI
# rather than codex, and reference the tag autoresearchclaw:runtime-opencode.
# That image had no recipe in this repository.
#
# It is a thin overlay: the base image already carries the CUDA stack, jax,
# gymnax and texlive. Comparing the two images layer by layer, the only
# difference is the opencode CLI, which lands at /opt/node/bin/opencode.
#
#   docker build -f real_eval/docker/autoresearchclaw_opencode_runtime.Dockerfile \
#     -t autoresearchclaw:runtime-opencode real_eval/docker
#
# Build autoresearchclaw:runtime-ready first.

FROM autoresearchclaw:runtime-ready

USER root

RUN npm install -g opencode-ai@latest 2>&1 | tail -3 \
 && opencode --version
