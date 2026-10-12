#!/usr/bin/env bash
# Installs the terminal client as the `lustjinn-tui` command, or updates it, from this checkout,
# on Linux or WSL. The Windows twin is install-tui.ps1.
#
#   ./scripts/install-tui.sh               tests first, then install
#   ./scripts/install-tui.sh --skip-tests  install as the code stands
#
# The command is a frozen copy with its own environment (`uv tool install`), so it keeps working
# whatever you do in the repo afterwards, until you run this again. Run it when you judge the code
# safe. Your settings and sign-in live apart from it (~/.config/lustjinn) and are kept.
set -euo pipefail

skip_tests=false
case "${1:-}" in
    "") ;;
    --skip-tests) skip_tests=true ;;
    *) echo "Usage: $0 [--skip-tests]" >&2; exit 2 ;;
esac

cd "$(dirname "$0")/.."

# A Windows checkout seen through /mnt/c shares its .venv with Windows: the tests' `uv run` would
# put a Linux environment in it and break the Windows side. Clone inside WSL instead.
case "$PWD" in
    /mnt/*)
        echo "This checkout is on the Windows drive ($PWD)." >&2
        echo "Clone the repo inside WSL (git clone https://github.com/argamboad/lustjinn.git ~/lustjinn) and run this from there." >&2
        exit 1 ;;
esac

if ! command -v uv >/dev/null 2>&1; then
    echo "uv is not installed: curl -LsSf https://astral.sh/uv/install.sh | sh, then open a new shell." >&2
    exit 1
fi

commit=$(git rev-parse --short HEAD)
branch=$(git branch --show-current)
if [ -n "$(git status --porcelain -- tui)" ]; then
    from="$commit on $branch, with uncommitted changes in tui/"
else
    from="$commit on $branch"
fi

if [ "$skip_tests" = false ]; then
    echo "Testing the terminal client ($from)..."
    uv run pytest tui/tests -q -p no:cacheprovider \
        || { echo "The terminal client's tests failed; nothing was installed." >&2; exit 1; }
fi

echo "Installing lustjinn-tui from $from..."
uv tool install --reinstall ./tui \
    || { echo "uv could not install the terminal client." >&2; exit 1; }

# Record what is installed, beside the client's own settings (where platformdirs puts them).
home_="${XDG_CONFIG_HOME:-$HOME/.config}/lustjinn"
mkdir -p "$home_"
echo "$from, installed $(date '+%Y-%m-%d %H:%M')" > "$home_/installed.txt"

# Where uv puts the command must be on the PATH for every new shell; added once, then left alone.
bin=$(uv tool dir --bin)
case ":$PATH:" in
    *":$bin:"*) ;;
    *)
        uv tool update-shell
        echo "Added $bin to your PATH. Open a new shell for it to take effect." ;;
esac

echo "Done: lustjinn-tui is $from. Run it from any new shell: lustjinn-tui"
