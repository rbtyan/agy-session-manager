#!/bin/sh
# Switch to AGY Session Manager on a single Left Arrow press ONLY when the agy
# prompt input box is empty. Otherwise, pass Left Arrow straight through to agy.

# 1. Inspect current pane mode and cursor position
INFO=$(tmux -L agym display-message -p '#{pane_in_mode} #{cursor_x} #{cursor_y}' 2>/dev/null || echo "1 99 0")
set -- $INFO
IN_MODE="${1:-1}"
CX="${2:-99}"
CY="${3:-0}"

# Must not be in copy-mode, and cursor must be at prompt start (col <= 2, right after "> ")
if [ "$IN_MODE" != "0" ] || [ "$CX" -gt 2 ] || [ "$CY" -lt 1 ]; then
    tmux -L agym send-keys Left
    exit 0
fi

# 2. Verify cursor sits inside a single-line agy prompt box (bounded by "────" above & below)
PREV_Y=$((CY - 1))
NEXT_Y=$((CY + 1))
ABOVE=$(tmux -L agym capture-pane -p -S "$PREV_Y" -E "$PREV_Y" 2>/dev/null)
BELOW=$(tmux -L agym capture-pane -p -S "$NEXT_Y" -E "$NEXT_Y" 2>/dev/null)

case "$ABOVE" in
    *"────"*) ;;
    *)
        tmux -L agym send-keys Left
        exit 0
        ;;
esac
case "$BELOW" in
    *"────"*) ;;
    *)
        tmux -L agym send-keys Left
        exit 0
        ;;
esac

# 3. Check whether the prompt line is empty (bare ">" or dimmed/colored placeholder)
PLAIN=$(tmux -L agym capture-pane -p -S "$CY" -E "$CY" 2>/dev/null)
TRIMMED=$(printf '%s' "$PLAIN" | sed 's/[[:space:]]*$//')
IS_EMPTY=0

if [ "$TRIMMED" = ">" ]; then
    IS_EMPTY=1
else
    case "$TRIMMED" in
        "> /"*)
            IS_EMPTY=0
            ;;
        "> "*)
            ANSI=$(tmux -L agym capture-pane -e -p -S "$CY" -E "$CY" 2>/dev/null)
            AFTER=$(printf '%s' "$ANSI" | sed 's/^[^>]*>[^ ]* //')
            ESC=$(printf '\033')
            case "$AFTER" in
                "${ESC}["*)
                    # Styled placeholder hint (e.g. "Accept-edits mode: ...")
                    IS_EMPTY=1
                    ;;
            esac
            ;;
    esac
fi

if [ "$IS_EMPTY" = "1" ]; then
    tmux -L agym select-window -t main:manager
else
    tmux -L agym send-keys Left
fi
