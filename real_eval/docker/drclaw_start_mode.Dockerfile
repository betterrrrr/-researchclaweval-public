# Dr. Claw Start Mode — Full Framework with Auto-Research Pipeline
FROM nvcr.io/nvidia/pytorch:25.11-py3

LABEL maintainer="ResearchClawEval" \
      description="Dr. Claw full framework (start mode) with GPU/CUDA support"

# Install Node.js 24.x and build tools for native modules
RUN apt-get update && apt-get install -y --no-install-recommends \
    libc-bin \
    ca-certificates \
    curl \
    build-essential \
    g++ \
    make \
    && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g npm@latest \
    && rm -rf /var/lib/apt/lists/*

# Create workspace directory
RUN mkdir -p /workspace/dr-claw /workspace/input /workspace/bin

# Copy Dr. Claw source (build context = dr-claw source dir)
COPY . /workspace/dr-claw/

# Install ONLY production npm dependencies — no devDeps, no frontend build
WORKDIR /workspace/dr-claw
RUN npm install --omit=dev 2>&1 | tail -5

# Rebuild native modules for Node.js (node-pty, sqlite3)
RUN cd node_modules/node-pty && npx node-gyp rebuild 2>&1 | tail -3 && \
    mkdir -p prebuilds/linux-x64 && cp build/Release/pty.node prebuilds/linux-x64/pty.node
RUN cd node_modules/better-sqlite3 && npx node-gyp rebuild 2>&1 | tail -3
RUN cd node_modules/sqlite3 && npx node-gyp rebuild 2>&1 | tail -3

# Pre-install Python ML packages needed for experiments
# Reinstall PyTorch for CUDA 13.2 (host driver compat with Blackwell GPUs)
RUN pip install --no-cache-dir --force-reinstall \
    --index-url https://download.pytorch.org/whl/cu132 \
    torch 2>&1 | tail -5

RUN pip install --no-cache-dir \
    transformers \
    tokenizers \
    datasets \
    numpy \
    scipy \
    scikit-learn \
    sentencepiece \
    wandb \
    2>&1 | tail -5

# Copy entrypoint script
COPY drclaw_start_entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/drclaw_start_entrypoint.sh

# Set environment
ENV HOME=/workspace \
    PATH=/workspace/dr-claw/node_modules/.bin:/opt/conda/bin:/usr/local/bin:/usr/bin:/bin:/sbin \
    PYTHONUNBUFFERED=1 \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility \
    PORT=3001 \
    HOST=0.0.0.0 \
    AUTO_RESEARCH_TASK_TIMEOUT_MS=7200000

# JWT_SECRET is deliberately not set here. The original image baked in a fixed
# development secret; supply one at run time instead:
#   docker run -e JWT_SECRET=$(openssl rand -hex 32) ...

WORKDIR /workspace

CMD ["drclaw_start_entrypoint.sh"]