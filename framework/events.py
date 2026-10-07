"""Event registry - connects ids in the browser back to Python functions.

While rendering, every on_click / on_enter callback is registered here and
replaced in the HTML by a small id:

    Button("Add", on_click=add_task)
        ->  <button data-pyui-click="7">Add</button>

When the browser sends "7" back to /event, App looks the id up here and
calls the original Python function.

The registry is rebuilt on every render (begin_render), so ids only need to
be valid for one render pass.  Ids themselves increase forever, so a stale
id from an old page can never accidentally hit a *different* callback - it
simply misses and nothing runs.
"""

from itertools import count

_handlers = {}
_ids = count()


def begin_render():
    """Drop the previous render's handlers; called before each render."""
    _handlers.clear()


def register(callback):
    """Store a Python callback and return the id to embed in the HTML."""
    handler_id = str(next(_ids))
    _handlers[handler_id] = callback
    return handler_id


def get(handler_id):
    """Find the callback for an id sent back by the browser (or None)."""
    if handler_id is None:
        return None
    return _handlers.get(str(handler_id))
