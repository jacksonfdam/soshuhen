"""Reads a comic page into panels and text blocks, for the reader to speak."""

import os

# ONNX Runtime reports usage to https://mobile.events.data.microsoft.com unless told not to: its
# 1.31 wheels carry that collector on Linux and macOS, and it starts when the runtime loads. This
# service exists so that nothing about a reader's pages leaves the machine, so the opt-out is set
# here, in the one module every import of this package passes through, and it is forced rather
# than defaulted so a stray setting cannot turn reporting back on.
os.environ["ORT_DISABLE_TELEMETRY"] = "1"
