# evoscientist:runtime-ready-mountaincar
#
# A thin overlay pinning the Topic-2 scientific stack.
#
# Topic 2 (MountainCar-Continuous) trains with JAX + gymnax via the frozen
# starter code in /workspace/src (train.py imports jax, gymnax, flax, optax,
# tensorflow_probability).  The plain evoscientist:runtime-ready image has NONE
# of that: neither /usr/local/bin/python3 nor /opt/venv/bin/python can import
# numpy, let alone jax or gymnax, and `find / -name gymnax` returns nothing.
# So training physically cannot run there and every MountainCar attempt ends
# with "checkpoints/ contains zero config-42-*.pkl".
#
# Versions are pinned to the set that is known to import cleanly (the same set
# used for the F06 Dr. Claw mountaincar image), so jax and
# tensorflow-probability cannot resolve into the incompatible pair that fails
# with "jax.interpreters.xla has no attribute pytype_aval_mappings".
FROM evoscientist:runtime-ready

USER root
RUN /usr/local/bin/uv pip install --python /opt/venv/bin/python \
        "numpy==2.2.6" "jax==0.6.2" "jaxlib==0.6.2" "gymnax==0.0.9" \
        "flax==0.10.7" "optax==0.2.8" "tensorflow-probability==0.25.0" \
        "dotmap==1.3.30" "tqdm==4.70.0" \
    && /opt/venv/bin/python -c "import numpy, jax, gymnax, flax, optax, tensorflow_probability as tfp; print('topic2 deps OK | jax', jax.__version__, '| gymnax', gymnax.__version__ if hasattr(gymnax,'__version__') else 'ok', '| numpy', numpy.__version__)"
