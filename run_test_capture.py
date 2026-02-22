import subprocess
import sys

try:
    result = subprocess.run(
        [r"venv\Scripts\python.exe", "-m", "pytest", "tests/test_analytics.py::TestDashboardEndpoint::test_dashboard_with_seeded_data", "-v", "--tb=long", "-s"],
        capture_output=True,
        text=True,
        check=False
    )
    with open("test_failures.txt", "w") as f:
        f.write(result.stdout)
        if result.stderr:
            f.write("\n\nSTDERR:\n" + result.stderr)
    print("Test output saved to test_failures.txt")
except Exception as e:
    print(f"Error: {e}")
