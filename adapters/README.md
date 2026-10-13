# Framework adapters

Each adapter pins an upstream repository and commit, records the documented
native entrypoint, and lists the minimal patch series required by the public
evaluation wrappers. The upstream source is never vendored here.

`candidate_requires_runtime_evidence` means the entrypoint is structurally
admissible but every result must still prove native ownership and provider
routing at runtime. `unsupported_non_native` entries may be inspected as
historical mappings but must not be scored or ranked as native results.

