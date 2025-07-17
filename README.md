# BracketBotOS

## Prerequisites
- [Install uv](https://docs.astral.sh/uv/getting-started/installation/): 

## Quickstart
1. Clone

```
git clone https://github.com/raghavauppuluri13/BracketBotOS.git
```

2. Install

```
cd BracketBotOS
uv sync
```

```
# takes around 5-10min
./install
```

3. Calibrate

```
manager calibrate --only drive
```

4. Run

In one terminal:
```
manager run --only camera drive mobile_joystick
```

In another terminal:

```
uv run apps/teleop.py
```

## Debug

- To prevent spamming of debug logs, you can access the .log files for all daemons with `debug-daemons` (or `debug-daemons > log` for easy copy pasting into LLMs)

- `debug-systemd hotspot` to debug the hotspot network logs
