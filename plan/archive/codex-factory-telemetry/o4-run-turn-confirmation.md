# O4 run_turn ACP turn-span — end-to-end confirmation

Created by an autonomous factory run to confirm that each ACP agent turn now emits a `run_turn` span (command / config_name / visit / stop_reason) into the Honeycomb `fabro` dataset, nested under the worker `run` span.
