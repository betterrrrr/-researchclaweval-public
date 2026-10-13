# dr-claw:runtime-ready-arc3
#
# The image the ARC-WBE-2026 runs used is an EvoScientist base with the
# ARC-WBE estimator dependencies layered on. It carried no recipe here, so
# this is a reconstruction.
#
# pandas/pyarrow are ADDED here because the arc wrapper's prompt promises them
# ("The runtime image provides pyarrow, pandas, numpy, and flopscope 0.8.0rc5")
# and the ARC-WBE dataset is parquet -- without them the framework cannot read
# the records at all.  Versions match the starterkit wheelhouse
# (/tmp/whest-starterkit/wheelhouse) so the tooling the task documents is what
# is actually installed.
FROM evoscientist:runtime-ready

USER root
# flopscope is on PyPI and also ships in the ARC-WBE starterkit wheelhouse,
# so it is fetched rather than vendored into this repository.
RUN /usr/local/bin/uv pip install --python /opt/venv/bin/python \
        "flopscope==0.8.0rc5" "pandas==2.3.2" "pyarrow==20.0.0" \
    && /opt/venv/bin/python -c "import flopscope, pandas, pyarrow; print('flopscope', flopscope.__version__, '| pandas', pandas.__version__, '| pyarrow', pyarrow.__version__)"

USER evosci
WORKDIR /workspace/dr-claw
CMD ["sleep", "3600"]
