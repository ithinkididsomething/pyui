# PyUI

A tiny browser UI framework written in **pure Python**. You describe a UI as a
tree of Python component objects, and PyUI turns it into a working web page in
the browser. Clicks and form fields travel back to Python, where plain Python
functions handle them.

No React, no Vue, no Flask/Django, no build step, no hand-written JavaScript —
Python standard library only.

---

## 1. What PyUI is

PyUI is five small modules (about 600 lines total) that let you write:

```python
Column(
    Text("My Todo List"),
    Button("Add Task", on_click=add_task)
)
```

…and have it run as a real, interactive page in a browser. The framework
provides:

| Requirement        | Where it lives                |
| ------------------ | ----------------------------- |
| Component tree     | `framework/element.py`        |
| HTML rendering     | `framework/renderer.py`       |
| State management   | `framework/state.py`          |
| Event handling     | `framework/events.py` + `framework/app.py` |
| HTTP server        | `server.py` (stdlib `http.server`) |
| Todo application    | `app/todo.py`                 |

## 2. Why it exists

To show — with code you can read in one sitting — what a UI framework actually
does under the hood: turn a description of a UI into HTML, wire user events
back into functions in the host language, and re-render when data changes.
Everything is intentionally small: no virtual DOM, no diffing, no lifecycle
methods, no JSX. The browser gets a fresh chunk of HTML after every event, and
that turns out to be enough.

## 3. Architecture

```text
pyui/
├── framework/
│   ├── __init__.py     # public API: Element, Text, Button, Input, Column, Row, State, App
│   ├── element.py      # component classes -> the tree (tag, props, children)
│   ├── renderer.py     # walks the tree, produces an HTML string
│   ├── state.py        # State: a reactive box holding one value
│   ├── events.py       # registry: HTML id  ->  Python callback
│   └── app.py          # App: renders pages, runs events, ships the HTML shell
├── app/
│   └── todo.py         # Todo app built only from PyUI components
├── server.py           # stdlib HTTP server: GET / and POST /event
├── test_pyui.py        # test suite: python test_pyui.py (stdlib only)
└── README.md
```

```text
┌────────────────────────────  browser  ────────────────────────────┐
│  HTML from PyUI          auto-generated JS in every page          │
│  <button data-pyui-click="7">  ──click──►  POST /event            │
│  <input  data-pyui-input="1">  ────────►  {handler:"7",           │
│                                             inputs:{"1":"text"}}  │
│  <div id="pyui-app">  ◄──HTML string──  replace innerHTML         │
└────────────────────────────────┬──────────────────────────────────┘
                                 │  HTTP (stdlib http.server)
┌────────────────────────────────▼──────────────────────────────────┐
│  server.py  ──►  App.handle_event()                               │
│                    1. events.get("7")       find the callback      │
│                    2. sync_states(inputs)   browser fields → State │
│                    3. callback()            run the Python code    │
│                    4. render(root())        rebuild the whole tree │
│                    5. return fresh HTML     sent back to browser   │
└───────────────────────────────────────────────────────────────────┘
```

**One click, step by step:**

```text
browser click  →  JS POSTs {handler id, input values} to /event
               →  handler id is validated against the last render
               →  input values are copied into their State objects
               →  Python callback for that id runs (may call State.set)
               →  App re-runs the root function (it reads current State)
               →  renderer walks the new tree → new HTML string
               →  HTML string goes back to the browser
               →  JS swaps the contents of #pyui-app (keeping focus/caret)
```

## 4. How the component tree works

Every component in `framework/element.py` is a plain object with three fields:

* `tag` — the HTML tag it becomes (`div`, `button`, `input`, …)
* `props` — a dict of properties (rendered as HTML attributes)
* `children` — nested components / text

```python
Column(                       # tag="div", flex-column style
    Text("Hello"),            # a text node
    Button("Click"),          # tag="button", child = Text("Click")
)
```

produces the tree:

```text
Column            tag="div"
├── Text          "Hello"
└── Button        tag="button"
    └── Text      "Click"
```

`Column` and `Row` are just `Element`s with a default flexbox `style`;
`Button` and `Input` are `Element`s with a known tag. Children may be lists,
raw strings (become `Text`), or `None`/`False` (disappear), so conditional
and repeated UI is easy to express:

```python
Column(
    Text("Always here"),
    show_extra and Text("Only when show_extra is true"),
)
```

## 5. How rendering works

`renderer.render(node)` walks the tree depth-first and returns a string.
That's the whole renderer:

```python
def render(node):
    if isinstance(node, Text):    return _render_text(node)     # escaped text
    if isinstance(node, Element): return _render_element(node)   # <tag ...>kids</tag>
```

Examples:

```python
Button("Click Me")                 ->  <button>Click Me</button>
Text("Count: 0")                   ->  Count: 0
Input(value=name, placeholder="x") ->  <input data-pyui-input="1" value="..." placeholder="x">
```

Two props never appear literally in the HTML:

* `on_click` / `on_enter` — registered with `events.py`, emitted as
  `data-pyui-click="<id>"` / `data-pyui-enter="<id>"`.
* `value` holding a `State` — the current value is written out *and*
  `data-pyui-input="<state id>"` is added so the browser can send field
  contents back to Python.

All text and attribute values are HTML-escaped, so user input can't inject
markup.

**Prop names** are normalised into HTML attribute names: underscores become
dashes (`aria_label` → `aria-label`), except where the underscore only
escapes a Python keyword (`class_` → `class`).

**Styling:** `App(root, title, styles="...")` injects extra CSS into the
page after PyUI's base stylesheet — markup still comes only from
components, but colours and spacing stay in ordinary CSS (see
`TODO_CSS` in `app/todo.py`).

## 6. How State works

`State` is a small reactive box:

```python
count = State(0)

count.value       # read
count.set(1)      # write -> notifies listeners -> app marked dirty
```

* Your root function reads `some_state.value` while building the tree, so the
  rendered HTML always reflects the current value.
* `set()` compares first (no change → no notification), then updates the value
  and calls every change listener. `App` registers one listener that sets
  `app.dirty = True`.
* Each `State` also gets a stable id, which is how input fields are matched
  back to their `State` when the browser posts data.

States are module-level variables in your application code — no providers,
no context, no ceremony.

## 7. How events work

1. While rendering, every callback is registered in `framework/events.py`
   and replaced by an id: `Button("Add", on_click=add_task)` becomes
   `<button data-pyui-click="7">Add</button>`.
2. Each page carries a tiny auto-generated script (see `PAGE` in
   `framework/app.py`) whose entire job is: on click/Enter, collect the values
   of all `data-pyui-input` fields, `POST {handler, inputs}` to `/event`, and
   replace `#pyui-app` with the response. **You never write JavaScript.**
3. `App.handle_event()` looks up the id first; only if it matches does it
   copy the field values into their `State`s and call the original Python
   function.
4. The handler registry is rebuilt on every render, and ids increase
   forever, so an event carrying an id from an *older* render (a click that
   raced with another re-render, or a second browser tab) matches nothing
   and is ignored entirely — including its input snapshot, so a stale
   request cannot overwrite newer state or act on a removed row. The
   response still returns the current HTML, which refreshes that page.

Input fields are synced at event time (not per keystroke) — that keeps the
wire chatter low and means you never lose focus while typing.

## 8. How re-rendering works

There is no diffing. After every event, `App`:

1. calls your root function again (`todo_app()` in the app),
2. which reads the *current* State values and builds a fresh component tree,
3. the renderer turns that tree into a brand-new HTML string,
4. the string goes back to the browser, which swaps `#pyui-app`'s contents.

So: **State.set → dirty → full re-render → new HTML → browser swaps it in.**
Rebuild-and-replace is simple enough that you can read the renderer in one
pass and reason about exactly what the browser will show.

On the browser side, the generated bridge remembers which input had focus
(and where the caret was) before swapping, then restores both afterwards;
an `autofocus` field is re-focused after every render, so you can type,
press Enter, and keep typing without touching the mouse.

## 9. Running the Todo app

Requires Python 3.x and nothing else (standard library only).

```bash
cd pyui
python server.py            # http://localhost:8000
python server.py 8080       # custom port
```

Then open <http://localhost:8000>. You can:

* type a task and click **Add Task** (or press **Enter**),
* click the circle to mark a task completed (it turns green with ✓ and the
  title gets a strikethrough); click it again to undo,
* click **×** to remove a task,
* use **Clear completed** in the footer (enabled only when something is done).

The window shows a live count badge, a "N of M left" summary, and an empty
state when nothing is left to do.

Run the test suite any time (standard library only, no pytest):

```bash
python test_pyui.py        # 13 checks: rendering, state, events,
                           # todo flow, escaping, concurrency, HTTP
```

Watch the terminal — every request is logged as `[pyui] ...`.

## 10. Example: a counter in PyUI

```python
from framework import App, Button, Column, State, Text

count = State(0)

def counter():
    return Column(
        Text(f"Count: {count.value}"),
        Button("+1", on_click=lambda: count.set(count.value + 1)),
    )

app = App(counter, title="Counter")

if __name__ == "__main__":
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    # ... or just reuse server.py by pointing it at `app`
```

Clicking the button posts the handler id to Python, `count.set()` runs, the
root function is called again with the new value, and the browser receives
`<div ...>Count: 1<button>+1</button></div>`.

---

## Design notes & limitations

* **Single-page, single-session.** The handler registry and states are global,
  so this is built for one browser tab, not many concurrent users. If a
  second tab sends an event from an older render, that one event is ignored
  (and its page refreshes) — never applied to the wrong thing.
* **Full re-render every event.** Perfect for small UIs; it would not scale to
  a huge DOM without diffing.
* **Callbacks must stay short.** The browser waits for the HTTP response, so
  a slow handler means a slow UI.
* **Deliberately omitted:** virtual DOM, reconciliation, component lifecycle,
  hooks, CSS-in-Python, routing, templating.

Ideas if you want to extend it: an `on_input` handler (update a `State` per
keystroke, re-render only the field), a `List` component, or Server-Sent
Events so Python can push updates without waiting for a click.
