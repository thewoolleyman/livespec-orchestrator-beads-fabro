# P2 FABRO_LOG=warn telemetry — end-to-end confirmation

Created by an autonomous factory run to confirm that OTLP telemetry is decoupled from the FABRO_LOG level: at FABRO_LOG=warn the factory span tree still exports to Honeycomb.
