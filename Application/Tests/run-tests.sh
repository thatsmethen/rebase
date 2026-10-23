#!/bin/sh
set -eu

# The default lane is deliberately independent of the caller's private setup.
case "${1-}" in
    --with-research)
        if [ "$#" -lt 2 ]; then
            echo 'Usage: run-tests.sh --with-research /absolute/external/root [swift test options]' >&2
            exit 2
        fi
        case "$2" in
            /*) ;;
            *) echo 'The research root must be an absolute path.' >&2; exit 2 ;;
        esac
        if [ ! -d "$2" ]; then
            echo 'The research root must be an existing directory.' >&2
            exit 2
        fi
        REBASE_RESEARCH_ROOT=$2
        export REBASE_RESEARCH_ROOT
        shift 2
        ;;
    --public)
        unset REBASE_RESEARCH_ROOT
        shift
        ;;
    *) unset REBASE_RESEARCH_ROOT ;;
esac

exec sh "$(dirname "$0")/../test-app.sh" "$@"
