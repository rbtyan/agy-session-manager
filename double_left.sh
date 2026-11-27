#!/bin/sh
# Detect intentional double-tap Left Arrow (60ms <= dt <= 350ms) to switch to
# the AGY Session Manager window, while letting single Left and held key-repeat
# (< 60ms) pass through normally to agy.

TS_FILE="/tmp/agym_${USER:-$(id -u)}_left_ts"
NOW=$(date +%s%3N 2>/dev/null || true)
case "$NOW" in
    *[!0-9]*|"")
        NOW=$(python3 -c 'import time; print(int(time.time() * 1000))')
        ;;
esac

PREV=0
if [ -f "$TS_FILE" ]; then
    PREV=$(cat "$TS_FILE" 2>/dev/null || echo 0)
fi

DIFF=$((NOW - PREV))

if [ "$DIFF" -ge 60 ] && [ "$DIFF" -le 350 ]; then
    rm -f "$TS_FILE"
    tmux -L agym select-window -t main:manager
else
    printf '%s' "$NOW" > "$TS_FILE"
    tmux -L agym send-keys Left
fi
