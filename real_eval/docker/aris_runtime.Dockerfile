# ARIS runtime image (F03).
#
# The upstream repository (wanshuiyin/Auto-claude-code-research-in-sleep) ships
# no Dockerfile, and the image the evaluation runs used was built from a base
# that is not recorded anywhere in this repository. This file is therefore a
# reconstruction, not a byte-for-byte copy.
#
# What the original image contained, read off its layer history:
#   * an Ubuntu-based CUDA image carrying node and the `codex` CLI
#   * an apt step switching to a local mirror, then installing
#     openssh-server, sudo and bash
#   * one unprivileged user, added to sudo with passwordless access
#   * sshd listening on 22, PasswordAuthentication on, PermitRootLogin off
# It contained no ARIS source and no COPY layer at all: the framework is
# rsync'd into the run workspace and mounted at /workspace by the shared runner
# (see real_eval/scripts/arc_framework_fullrun.sh), so the image only has to
# provide a working codex environment.
#
# This reconstruction supplies the base toolchain explicitly rather than
# depending on an unidentified base. Verify it by building and comparing
# behaviour against an existing aris:runtime-ready if you have one.
#
#   docker build -f real_eval/docker/aris_runtime.Dockerfile \
#     -t aris:runtime-ready real_eval/docker

FROM nvcr.io/nvidia/pytorch:25.11-py3

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

# The original image had a single unprivileged user with a password baked in.
# Take the account name from a build arg and the password from a secret, so no
# credential is committed here.
ARG USERNAME=runner
ARG UID=2001
ARG GID=2001

USER root

# node + codex: the original base supplied these and the ARIS wrapper invokes
# `codex exec` inside the container.
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && npm install -g @openai/codex \
 && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /var/lib/apt/lists/partial \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      openssh-server \
      sudo \
      bash \
 && mkdir -p /var/run/sshd \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd -g ${GID} ${USERNAME} \
 && useradd -m -u ${UID} -g ${GID} -s /bin/bash ${USERNAME} \
 && usermod -aG sudo ${USERNAME} \
 && echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/${USERNAME} \
 && chmod 0440 /etc/sudoers.d/${USERNAME}

# The original image baked a fixed password into this layer. Do not reproduce
# that: the evaluation path never uses SSH (the runner invokes the container as
# root with --user 0:0), so the account is locked instead. If you want to reach
# this container over SSH, set a key in authorized_keys rather than a password.
RUN passwd -l "${USERNAME}"

RUN sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config \
 && sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config \
 && sed -i 's/^#\?PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config \
 && sed -i 's@^#\?AuthorizedKeysFile.*@AuthorizedKeysFile .ssh/authorized_keys@' /etc/ssh/sshd_config

ENV HOME=/home/${USERNAME}
WORKDIR /home/${USERNAME}
EXPOSE 22
CMD ["/usr/sbin/sshd", "-D"]
