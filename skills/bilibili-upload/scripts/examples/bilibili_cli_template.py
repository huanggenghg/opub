from __future__ import annotations

import shlex
import subprocess


def run_command(command: list[str]) -> None:
    print("Running:", " ".join(shlex.quote(part) for part in command))
    subprocess.run(command, check=True)


def main() -> None:
    account = "account_a"
    # account_name is user-defined. One account_name maps to one account file.
    # You can prepare multiple account names and run them in parallel.
    # Bilibili login must be run by the user in a local interactive terminal.

    commands = [
        # Login: user must run this in a real terminal, not by an agent
        # ["sau", "bilibili", "login", "--account", account],
        ["sau", "bilibili", "check", "--account", account],
        [
            "sau",
            "bilibili",
            "upload-video",
            "--account",
            account,
            "--file",
            "videos/demo.mp4",
            "--title",
            "Bilibili video from Python",
            "--desc",
            "Bilibili video description from Python",
            "--tid",
            "121",  # 121 = 体育-足球
            "--tags",
            "cli,video",
        ],
    ]

    for command in commands:
        run_command(command)


if __name__ == "__main__":
    main()
