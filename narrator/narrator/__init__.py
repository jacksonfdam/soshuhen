"""Reads a comic page into panels and text blocks, for the reader to speak."""

import os

# ONNX Runtime reports usage to https://mobile.events.data.microsoft.com unless told not to: its
# 1.31 wheels carry that collector on Linux and macOS, and it starts when the runtime loads. This
# service exists so that nothing about a reader's pages leaves the machine, so the opt-out is set
# here, in the one module every import of this package passes through, and it is forced rather
# than defaulted so a stray setting cannot turn reporting back on.
os.environ["ORT_DISABLE_TELEMETRY"] = "1"

# OpenCV refuses to decode an image of more pixels than this. Its own default is over a thousand
# million: a file of a few hundred kilobytes, served by a third-party site, can ask for gigabytes
# of memory and minutes of recognition. The longest strip seen in a real library is thirteen
# million pixels. Set here for the same reason as the line above: the decoder reads it when it
# first loads, and this module is imported before anything that loads it.
os.environ["OPENCV_IO_MAX_IMAGE_PIXELS"] = "50000000"
