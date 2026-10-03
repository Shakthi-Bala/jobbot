## no-estimated-numbers

**Rule:** Only metrics present in `profile.yaml` appear.

Never estimate, round up, or infer a number. A metric whose value is `null` means: no number. Say what was done without quantifying it. Numbers that are part of names (a job title, "ROS 2") are fine.

_Enforced by:_ `checks/numbers_match.py` fails on any number not found in the facts a line cites.
