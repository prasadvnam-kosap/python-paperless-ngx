"""Python LOADED tracer. Put this directory on PYTHONPATH; CPython imports it automatically.

    PYTHONPATH=usage/capture DEPPROOF_TRACE_DIR=traces uv run pytest

WHY sitecustomize AND NOT `-X importtime`: importtime writes a human-readable table to stderr,
which the test runner captures and interleaves, and it names MODULES, not distributions. The
module-to-distribution step is the hard part and it is the part that must not be guessed --
`yaml` comes from PyYAML, `pkg_resources` from setuptools, `attr` from attrs. So this resolves
in-process with importlib.metadata.packages_distributions(), which is stdlib from 3.10 and is
the authority rather than an inference.

WHY ONE FILE PER PID: netbox's declared command is `manage.py test --parallel`, which FORKS
worker processes. Django reports one aggregate result, so a single output file looks complete
while holding one worker's imports. That is the JVM's `%p` lesson (CS-8 #2) in another
ecosystem, and it is easier to miss here because nothing warns you.

WHY AT EXIT AND NOT AT IMPORT: an import hook changes import semantics under test; reading
sys.modules once, at exit, does not. Loading is an upper bound on use either way -- this
measures LOADED, and the axis is named that for a reason.
"""

import atexit
import os
import sys


def _dump():
    trace_dir = os.environ.get("DEPPROOF_TRACE_DIR")
    if not trace_dir:
        return
    try:
        os.makedirs(trace_dir, exist_ok=True)

        from importlib.metadata import packages_distributions, version

        # module top-level name -> [distribution names]
        mapping = packages_distributions()

        found = {}
        unresolved = set()
        for mod in list(sys.modules):
            if not mod or mod.startswith("_"):
                continue
            top = mod.split(".", 1)[0]
            dists = mapping.get(top)
            if not dists:
                # stdlib, first-party, or a namespace package importlib cannot attribute.
                # Recorded rather than dropped: an unattributed import that silently vanishes
                # biases the result toward "never loaded", which is the unsafe direction.
                if top not in sys.stdlib_module_names:
                    unresolved.add(top)
                continue
            for dist in dists:
                if dist not in found:
                    try:
                        found[dist] = version(dist)
                    except Exception:
                        found[dist] = "UNKNOWN"

        path = os.path.join(trace_dir, f"python-{os.getpid()}.txt")
        with open(path, "w") as fh:
            fh.write(f"# pid {os.getpid()} argv={' '.join(sys.argv[:3])}\n")
            for name in sorted(found):
                fh.write(f"{name}=={found[name]}\n")
            # Written to the SAME file so it cannot be read without being seen.
            for top in sorted(unresolved):
                fh.write(f"# unresolved-module {top}\n")
    except Exception as e:                       # never break the suite being measured
        sys.stderr.write(f"[depproof-trace] shim failed: {e}\n")


atexit.register(_dump)
