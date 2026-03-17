import urllib.request

try:
    job_id = "66463241600"
    log_req = urllib.request.Request(
        f"https://api.github.com/repos/avianthonf/RetailIQ/actions/jobs/{job_id}/logs",
        headers={"Accept": "application/vnd.github.v3+json"},
    )

    with urllib.request.urlopen(log_req) as log_response:
        logs = log_response.read().decode("utf-8")

        in_alembic = False
        captured = []
        for line in logs.split("\n"):
            if " almebic check" in line.lower() or "OUTPUT=$(alembic check" in line:
                in_alembic = True
            if in_alembic:
                captured.append(line)
            if in_alembic and ("Error: Process completed" in line or "Exit code: 1" in line):
                break

        print("\n".join(captured[-100:]))
except Exception as e:
    print(f"Error: {e}")
