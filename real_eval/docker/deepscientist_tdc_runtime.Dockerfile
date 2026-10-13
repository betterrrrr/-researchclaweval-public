FROM deepscientist:runtime-ready

USER root

# Seed the exact workspace-relative home used by formal Topic 5 runs. The
# archive preserves absolute venv paths while keeping each run workspace fresh.
RUN rm -rf /workspace/.deepscientist \
    && mkdir -p /workspace \
    && ds --home /workspace/.deepscientist init \
    && tar -C /workspace -cpf /opt/deepscientist-tdc-home.tar .deepscientist \
    && rm -rf /workspace/.deepscientist

ENV UV_OFFLINE=1
