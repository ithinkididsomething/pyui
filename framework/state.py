"""Reactive state - PyUI's State class.

A State is a small box holding a value:

    count = State(0)
    count.value        # read
    count.set(1)       # write  -> marks the UI as needing a re-render

Reads happen while a component tree is being built (inside your root
function), so whatever the value is at render time is what gets displayed.

Because a browser cannot be pushed to by Python between requests, the
actual "re-render and send" step happens at the end of the event loop in
app.py - but every State.set() notifies listeners so the app knows the UI
has become stale.  No magic, no diffing: set() -> dirty -> full re-render.
"""

from itertools import count

# Stable id per State, embedded in the HTML as data-pyui-input="<id>"
# so input fields can be matched back to their State when the browser
# sends data to Python.
_states = {}
_ids = count()

# Callables notified on every State.set() (App registers one).
_listeners = []


def add_change_listener(fn):
    """Register fn(state) to be called whenever any State changes."""
    _listeners.append(fn)


def state_by_id(sid):
    """Look a State up by its stable id (used by the event bridge)."""
    return _states.get(str(sid))


def sync_states(values):
    """Apply input values collected from the browser: {state_id: string}."""
    for sid, raw in values.items():
        state = state_by_id(sid)
        if state is not None:
            state.set(raw)


class State:
    """A reactive box holding one value."""

    def __init__(self, value):
        self._id = str(next(_ids))
        self._value = value
        _states[self._id] = self

    @property
    def id(self):
        """Stable id - this is what ends up in the HTML for input fields."""
        return self._id

    @property
    def value(self):
        """Current value (read this inside your root render function)."""
        return self._value

    def set(self, new_value):
        """Change the value and tell listeners the UI needs re-rendering."""
        if new_value == self._value:
            return  # no actual change, nothing to re-render
        self._value = new_value
        for fn in _listeners:
            fn(self)

    def __repr__(self):
        return f"State({self._value!r})"
