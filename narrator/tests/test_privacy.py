import os
import subprocess
import sys


def _after_import(environment: dict[str, str]) -> str:
    """What a fresh interpreter has in ORT_DISABLE_TELEMETRY once the package is imported."""
    program = "import os, narrator; print(os.environ.get('ORT_DISABLE_TELEMETRY'))"
    result = subprocess.run(
        [sys.executable, "-c", program], env=environment, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def test_the_runtime_is_told_not_to_report_before_it_can_load():
    clean = {key: value for key, value in os.environ.items() if key != "ORT_DISABLE_TELEMETRY"}

    assert _after_import(clean) == "1"


def test_an_environment_that_asks_for_telemetry_does_not_get_it():
    assert _after_import({**os.environ, "ORT_DISABLE_TELEMETRY": "0"}) == "1"


def test_the_decoder_is_given_a_pixel_limit_before_it_can_load():
    program = "import os, narrator; print(os.environ.get('OPENCV_IO_MAX_IMAGE_PIXELS'))"
    result = subprocess.run(
        [sys.executable, "-c", program],
        env={
            key: value for key, value in os.environ.items() if key != "OPENCV_IO_MAX_IMAGE_PIXELS"
        },
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "50000000"
