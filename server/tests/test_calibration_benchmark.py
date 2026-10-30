"""
Calibration Benchmark Integration Test.
Verifies that fixtures/calibrate.py executes successfully, satisfies all
acceptance criteria (genuine pass rate, impostor rejection rate, flatness gate rejection,
and flat score rejection), and exits with status 0.
"""

import os
import subprocess
import sys


def test_calibration_benchmark_executes_and_passes():
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    script_path = os.path.join(repo_root, "fixtures", "calibrate.py")
    env = os.environ.copy()
    env["PYTHONPATH"] = repo_root

    res = subprocess.run(
        [sys.executable, script_path],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
        env=env,
    )

    assert res.returncode == 0, f"Benchmark failed with exit code {res.returncode}:\n{res.stdout}\n{res.stderr}"
    assert "Pass Rate: 100%" in res.stdout
    assert "Rejection Rate: 100%" in res.stdout
    assert "Score Rejection Rate: 100%" in res.stdout
    assert "Flatness Gate Rejection Rate:       100% (flatPrintPassed=False)" in res.stdout
    assert "CALIBRATION BENCHMARK SUCCESS: All criteria verified." in res.stdout
