# Dr. Claw Runtime with GPU/CUDA support
FROM nvcr.io/nvidia/pytorch:25.11-py3

LABEL maintainer="ResearchClawEval" \
      description="Dr. Claw runtime with CUDA/GPU support for BabyLM experiments"

# Install Node.js 24.x and ldconfig for GPU detection
RUN apt-get update && apt-get install -y --no-install-recommends \
    libc-bin \
    ca-certificates \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g npm@latest \
    && rm -rf /var/lib/apt/lists/*

# Create workspace directory
RUN mkdir -p /workspace/dr-claw /workspace/input /workspace/bin

# Copy Dr. Claw source
COPY dr-claw/ /workspace/dr-claw/

# Install Dr. Claw npm dependencies
WORKDIR /workspace/dr-claw
RUN npm install --omit=dev 2>&1 || echo "npm install had warnings, continuing"

# Pre-install Python ML packages with CUDA support
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

# Set environment
ENV HOME=/workspace \
    PATH=/workspace/dr-claw/node_modules/.bin:/opt/conda/bin:/usr/local/bin:/usr/bin:/bin:/sbin \
    PYTHONUNBUFFERED=1 \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

WORKDIR /workspace

CMD ["npm", "run", "start"]
