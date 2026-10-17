from app.cli import COMMANDS


def test_commands_used_by_scheduled_jobs_exist():
    # Must match the --command of each Cloud Run Job; renaming a command
    # here without updating its job breaks the job silently until it runs.
    expected = {
        "cleanup-refresh-tokens",
        "cleanup-stale-attachments",
        "cleanup-rate-limits",
    }
    assert expected <= COMMANDS.keys()
