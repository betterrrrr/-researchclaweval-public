# dr-claw:runtime-ready-mountaincar
#
# The Topic-2 contract's requirements.txt lists jax[cuda12], gymnax, flax,
# optax, tensorflow_probability, dotmap, tqdm WITHOUT pins.  Resolved
# unpinned into the image's system python 3.12, pip picks a jax/tensorflow-
# probability pair that blows up at import:
#
#   AttributeError: module 'jax.interpreters.xla' has no attribute
#   'pytype_aval_mappings'
#
# (that is TFP reaching into a jax internals API the installed jax no longer
# has).  The framework then correctly refuses to fabricate checkpoints and the
# run ends with no score.  F05 gets past this only because its model happened
# to build its own venv.
#
# Pin the set that is known to import cleanly, so the framework can train on a
# fixed, reproducible toolchain. CPU jax: this topic runs with
# FRAMEWORK_DISABLE_GPU=1.
# framework can train on a fixed, reproducible toolchain.  CPU jax: this topic
# runs with FRAMEWORK_DISABLE_GPU=1.
FROM dr-claw:runtime-ready

USER root
RUN python -m pip install --no-cache-dir \
        "jax==0.6.2" "jaxlib==0.6.2" "gymnax==0.0.9" "flax==0.10.7" \
        "optax==0.2.8" "tensorflow-probability==0.25.0" "numpy==2.2.6" \
        "dotmap==1.3.30" "tqdm==4.70.0" \
    && python -c "import jax, gymnax, flax, optax, tensorflow_probability as tfp, numpy; print('mountaincar deps OK | jax', jax.__version__, '| tfp', tfp.__version__, '| numpy', numpy.__version__)"
