# BracketBotOS

## Prerequisites
- [Install uv](https://docs.astral.sh/uv/getting-started/installation/): 

## Quickstart
1. Clone


2. Install

```
uv sync
```

```
# takes around 5-10min
./install
```

3. Run

In one terminal:
```
manager --only camera drive mobile_joystick
```

In another terminal:

```
uv run apps/teleop.py
```

## Debug

- To prevent spamming of debug logs, you can access the .log files for all daemons with `debug-daemons` (or `debug-daemons > log` for easy copy pasting into LLMs)

- `debug-systemd hotspot` to debug the hotspot network logs
