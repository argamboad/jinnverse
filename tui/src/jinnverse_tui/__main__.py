"""`python -m jinnverse_tui`: the same as the `jinnverse-tui` command.

The way in for a debugger. Not `python -m jinnverse_tui.app`: that runs app.py as `__main__`, a
second copy of the module beside the `jinnverse_tui.app` the screens import, so the app would not
be the `JinnverseApp` they look for. Importing it here keeps one copy.
"""

from jinnverse_tui.app import main

main()
