"""PyUI test suite - run with:  python test_pyui.py

Standard library only (no pytest).  Covers rendering, state, events, the
Todo flow, escaping, concurrency, and the HTTP layer.  Exits non-zero on
failure so it can be used as a smoke check.
"""

import contextlib
import io
import json
import re
import sys
import threading
import traceback
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from html.parser import HTMLParser

import framework.app as app_module
import server as server_module
from app import todo
from app.todo import app
from framework import App, Button, Column, Element, Input, Row, State, Text
from framework import events, state as state_module
from framework.renderer import render


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def check_well_formed(html):
    """Return a list of tag-balance problems in `html`."""
    void = {"area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr"}

    class Balance(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack, self.errors = [], []

        def handle_starttag(self, tag, attrs):
            if tag not in void:
                self.stack.append(tag)

        def handle_endtag(self, tag):
            if not self.stack:
                self.errors.append(f"stray </{tag}>")
            elif self.stack[-1] != tag:
                self.errors.append(f"</{tag}> closes <{self.stack[-1]}>")
            else:
                self.stack.pop()

    parser = Balance()
    parser.feed(html)
    parser.errors += [f"unclosed <{t}>" for t in parser.stack]
    return parser.errors


def reset():
    todo.tasks.set([])
    todo.draft.set("")


def click_id(html, label):
    m = re.search(r'data-pyui-click="(\d+)"[^>]*>' + re.escape(label) + r"</button>", html)
    assert m, f"button {label!r} not found"
    return m.group(1)


def labeled_click_id(html, aria_label_prefix):
    m = re.search(
        r'data-pyui-click="(\d+)"[^>]*aria-label="' + re.escape(aria_label_prefix), html
    )
    assert m, f"button aria-label~={aria_label_prefix!r} not found"
    return m.group(1)


def input_sid(html):
    m = re.search(r'data-pyui-input="(\d+)"', html)
    assert m, "no State-backed input found"
    return m.group(1)


def enter_id(html):
    m = re.search(r'data-pyui-enter="(\d+)"', html)
    assert m, "no on_enter hook found"
    return m.group(1)


def fire(handler, inputs=None):
    return app.handle_event({"handler": handler, "inputs": inputs or {}})


def add_via_click(html, text):
    return fire(click_id(html, "Add Task"), {input_sid(html): text})


def add_via_enter(html, text):
    return fire(enter_id(html), {input_sid(html): text})


def toggle_first(html, task_is_done):
    label = "Mark as not done" if task_is_done else "Mark as done"
    return fire(labeled_click_id(html, label), {input_sid(html): ""})


def remove_first(html):
    return fire(labeled_click_id(html, "Remove "), {input_sid(html): ""})


def http_get(url):
    try:
        with urllib.request.urlopen(url) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def http_post(url, data):
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def start_server():
    server_module.PyUIRequestHandler.log_message = lambda *a, **k: None  # quiet tests
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server_module.PyUIRequestHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


# ----------------------------------------------------------------------
# 1. Component tree + renderer
# ----------------------------------------------------------------------
def test_render_basics():
    assert render(Button("Click Me")) == "<button>Click Me</button>"
    assert render(Text("Hello")) == "Hello"
    assert render(Input(placeholder="Type")) == '<input value="" placeholder="Type">'
    assert render(Element(Text("plain"))) == "<div>plain</div>"

    nested = render(Column(Text("Hello"), Button("Click")))
    assert nested == (
        '<div style="display:flex;flex-direction:column;gap:8px;">'
        "Hello<button>Click</button></div>"
    )

    row = render(Row(Text("a"), Text("b")))
    assert row.startswith('<div style="display:flex;flex-direction:row;')

    # strings auto-wrap into Text, lists flatten, None/False vanish
    assert render(Column("raw", [Text("a"), Text("b")], None, False and Text("x"))) == (
        '<div style="display:flex;flex-direction:column;gap:8px;">rawab</div>'
    )
    assert render(Column(False and Text("x"), Text("ok"))).endswith("ok</div>")


def test_render_escaping_and_props():
    assert render(Text("<b>x</b>")) == "&lt;b&gt;x&lt;/b&gt;"
    assert render(Button("x", class_="a")) == '<button class="a">x</button>'
    assert render(Button("x", disabled=True)) == "<button disabled>x</button>"
    assert render(Button("x", disabled=False)) == "<button>x</button>"
    assert render(Text("styled", style="color:red")) == '<span style="color:red">styled</span>'

    # attr values are quote-escaped, State value is rendered from .value
    out = render(Input(value='a"b', aria_label="field"))
    assert 'value="a&quot;b"' in out
    assert 'aria-label="field"' in out

    # Column keeps its default layout and lets user style win (CSS last-wins)
    col = Column(Text("a"), style="gap:20px;")
    assert col.props["style"].endswith("gap:8px;gap:20px;")


def test_state():
    s = State(1)
    assert s.value == 1
    s.set(2)
    assert s.value == 2
    assert re.fullmatch(r"\d+", s.id)
    assert State("a").id != State("b").id

    seen = []
    state_module.add_change_listener(lambda st: seen.append(st.value) if st is s else None)
    s.set(3)
    assert seen == [3], "set() must notify listeners on a real change"
    s.set(3)
    assert seen == [3], "set() with the same value must not notify"


def test_event_registry():
    events.begin_render()

    def cb():
        pass

    hid = events.register(cb)
    assert events.get(hid) is cb
    assert events.get("nope") is None
    assert events.get(None) is None
    events.begin_render()
    assert events.get(hid) is None, "old render's handlers must be dropped"


# ----------------------------------------------------------------------
# 2. Todo application flow
# ----------------------------------------------------------------------
def test_todo_flow():
    h = app.render_page()
    assert "0 tasks" in h and "Nothing here yet" in h
    assert "Clear completed" not in h, "footer hidden while the list is empty"
    assert "My Todo List" in h
    assert "Built with PyUI" not in h and "hand-written JavaScript" not in h

    # add by clicking (nothing completed yet -> Clear must stay disabled)
    h = add_via_click(h, "Buy milk")
    assert "Buy milk" in h and 'value=""' in h
    assert 'data-pyui-key="task-0"' in h, "new row carries a stable key for the pop-in"
    assert 'data-pyui-from="typebar"' in h, "bubble detaches from the type bar"
    assert "1 of 1 left" in h and ">1 task<" in h
    assert re.search(r'data-pyui-click="\d+"[^>]*disabled[^>]*>Clear completed', h)

    # add by pressing Enter
    h = add_via_enter(h, "Walk dog")
    assert "Walk dog" in h and "2 of 2 left" in h and ">2 tasks<" in h
    assert 'data-pyui-key="task-1"' in h

    # whitespace-only input must not create a task
    h2 = add_via_click(h, "   ")
    assert "2 of 2" in h2 and h2.count("class=\"task-title") == 2

    # complete the first task
    h = toggle_first(h2, task_is_done=False)
    assert "task-done" in h and "1 of 2 left" in h
    assert 'aria-label="Mark as not done"' in h
    assert not re.search(r'data-pyui-click="\d+"[^>]*disabled[^>]*>Clear completed', h)

    # remove the first task (the completed one)
    h = remove_first(h)
    assert "Buy milk" not in h and "Walk dog" in h and "1 of 1 left" in h

    # complete the rest, then clear completed
    h = toggle_first(h, task_is_done=False)
    assert "All done" in h
    h = fire(click_id(h, "Clear completed"), {input_sid(h): ""})
    assert "Nothing here yet" in h and "0 tasks" in h
    assert "Clear completed" not in h, "footer hidden again when empty"


def test_stale_event_is_ignored():
    """An event id from an older render must not run or clobber input state."""
    reset()
    h1 = app.render_page()
    stale = click_id(h1, "Add Task")
    h2 = add_via_click(h1, "Buy milk")           # draft cleared, 1 task

    h3 = fire(stale, {input_sid(h1): "POISON"})  # replay old id + old inputs
    assert "POISON" not in h3, "stale input snapshot must not leak into State"
    assert 'value=""' in h3, "stale event must not refill the input"
    assert "1 of 1 left" in h3, "stale event must not run the callback"


def test_escaping_and_unicode():
    reset()
    h = app.render_page()
    text = 'café "q" & <tag> → done'
    h = add_via_click(h, text)
    assert "<tag>" not in h
    assert "&lt;tag&gt;" in h and "café" in h
    # the title lands in the task row, fully escaped (input is cleared again)
    assert 'class="task-title">café &quot;q&quot; &amp; &lt;tag&gt; → done</span>' in h
    assert 'value=""' in h
    # still fully functional with the weird title
    h = toggle_first(h, task_is_done=False)
    assert "task-done" in h


def test_page_shell_and_styles():
    reset()
    h = app.render_page()
    assert ".btn-primary" in h, "App(styles=...) CSS must be injected"
    assert "setSelectionRange" in h and "data-pyui-input" in h, "focus bridge present"
    assert "<noscript>" in h and "Please enable JavaScript" in h
    assert "autofocus" in h and 'maxlength="120"' in h
    assert "<title>Todo</title>" in h
    assert "@keyframes pyui-in" in h and "animation: pyui-in" in h, "opening animation"
    assert "prefers-reduced-motion" in h
    assert "backdrop-filter" in h, "glass Add Task button"
    assert "data-pyui-key" in h and "el.animate(" in h, "bubble pop-in for new keys"
    assert 'data-pyui-key="typebar"' in h and "getBoundingClientRect" in h
    assert "data-pyui-pop" in h, "type bar arms the extend animation on click"
    assert "clipPath" in h and "inset(62%" in h, "the bar breaks apart at the seam"


def test_title_escaping():
    saved = app_module._current_app
    try:
        weird = App(lambda: Text("hi"), title="<script>alert(1)</script>")
        page = weird.render_page()
        title = page.split("<title>")[1].split("</title>")[0]
        assert title == "&lt;script&gt;alert(1)&lt;/script&gt;"
    finally:
        app_module._current_app = saved


def test_concurrent_events():
    """Parallel events must serialise cleanly: no crashes, no corrupt state."""
    reset()
    h = app.render_page()
    handler = click_id(h, "Add Task")
    sid = input_sid(h)

    results, errors = [], []

    def worker(i):
        try:
            results.append(fire(handler, {sid: f"task-{i}"}))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"concurrent events raised: {errors}"
    assert len(results) == 12
    assert all("<div" in r for r in results), "every response must be valid HTML"
    # The first event wins; the rest carry ids that were invalidated by the
    # re-render, so they are safely ignored instead of double-applying.
    assert len(todo.tasks.value) == 1
    assert todo.tasks.value[0]["title"].startswith("task-")


def test_html_is_well_formed():
    reset()
    h = app.render_page()
    assert not check_well_formed(h), check_well_formed(h)

    h = add_via_click(h, "one")
    h = add_via_enter(h, "two")
    h = toggle_first(h, task_is_done=False)   # complete "one"
    h = remove_first(h)                       # remove "one"
    h = toggle_first(h, task_is_done=False)   # complete "two"
    h = fire(click_id(h, "Clear completed"), {input_sid(h): ""})
    errors = check_well_formed(h)
    assert not errors, errors
    assert "Nothing here yet" in h


# ----------------------------------------------------------------------
# 3. HTTP layer
# ----------------------------------------------------------------------
def test_http_end_to_end():
    reset()
    srv, base = start_server()
    try:
        status, page = http_get(base + "/")
        assert status == 200 and "My Todo List" in page and 'id="pyui-app"' in page

        status, _ = http_get(base + "/nope")
        assert status == 404

        # add a task over real HTTP (using the ids from the loaded page)
        payload = json.dumps(
            {"handler": click_id(page, "Add Task"), "inputs": {input_sid(page): "Over HTTP"}}
        ).encode("utf-8")
        status, body = http_post(base + "/event", payload)
        assert status == 200 and "Over HTTP" in body and "1 of 1 left" in body

        # stale id over HTTP: no crash, no clobber
        payload = json.dumps(
            {"handler": click_id(page, "Add Task"), "inputs": {input_sid(page): "POISON"}}
        ).encode("utf-8")
        status, body = http_post(base + "/event", payload)
        assert status == 200 and "POISON" not in body and "1 of 1 left" in body

        # malformed JSON body must not crash the server
        status, body = http_post(base + "/event", b"{not json")
        assert status == 200 and "My Todo List" in body

        status, _ = http_post(base + "/wrong", b"{}")
        assert status == 404
    finally:
        srv.shutdown()
        srv.server_close()


def test_server_error_pages():
    """A raising root function must produce a friendly 500 page (details in the log)."""
    saved_app = server_module.app
    saved_current = app_module._current_app

    def boom():
        raise RuntimeError("boom-from-root")

    try:
        server_module.app = App(boom, title="Broken")
        srv, base = start_server()
        try:
            # the server logs the traceback on purpose; keep test output clean
            with contextlib.redirect_stderr(io.StringIO()):
                status, body = http_get(base + "/")
                assert status == 500 and "Something went wrong" in body
                assert "boom-from-root" not in body, "no raw traceback in the browser"

                status, body = http_post(base + "/event", b'{"handler":"999999"}')
                assert status == 500 and "Something went wrong" in body
                assert "boom-from-root" not in body
        finally:
            srv.shutdown()
            srv.server_close()
    finally:
        server_module.app = saved_app
        app_module._current_app = saved_current


def test_wsgi_entrypoint():
    """The serverless WSGI entrypoint must serve pages, events, 404s and errors."""
    import wsgi as wsgi_module

    reset()
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    # GET / -> full page
    environ = {"REQUEST_METHOD": "GET", "PATH_INFO": "/",
               "wsgi.input": io.BytesIO(b"")}
    page = b"".join(wsgi_module.app(environ, start_response)).decode("utf-8")
    assert captured["status"].startswith("200")
    assert "My Todo List" in page

    # POST /event -> adds a task through the same machinery as server.py
    payload = json.dumps({
        "handler": click_id(page, "Add Task"),
        "inputs": {input_sid(page): "Served over WSGI"},
    }).encode("utf-8")
    environ = {"REQUEST_METHOD": "POST", "PATH_INFO": "/event",
               "CONTENT_LENGTH": str(len(payload)),
               "wsgi.input": io.BytesIO(payload)}
    body = b"".join(wsgi_module.app(environ, start_response)).decode("utf-8")
    assert captured["status"].startswith("200")
    assert "Served over WSGI" in body

    # malformed JSON is tolerated (falls back to an empty payload)
    raw = b"not json"
    environ = {"REQUEST_METHOD": "POST", "PATH_INFO": "/event",
               "CONTENT_LENGTH": str(len(raw)),
               "wsgi.input": io.BytesIO(raw)}
    body = b"".join(wsgi_module.app(environ, start_response)).decode("utf-8")
    assert captured["status"].startswith("200")
    assert "My Todo List" in body

    # 404 for anything else
    environ = {"REQUEST_METHOD": "GET", "PATH_INFO": "/nope",
               "wsgi.input": io.BytesIO(b"")}
    wsgi_module.app(environ, start_response)
    assert captured["status"].startswith("404")

    # a raising root function -> friendly 500, no traceback in the body
    saved_app = wsgi_module.todo_app
    saved_current = app_module._current_app

    def boom():
        raise RuntimeError("boom-from-wsgi")

    try:
        wsgi_module.todo_app = App(boom, title="Broken")
        environ = {"REQUEST_METHOD": "GET", "PATH_INFO": "/",
                   "wsgi.input": io.BytesIO(b"")}
        with contextlib.redirect_stderr(io.StringIO()):
            body = b"".join(wsgi_module.app(environ, start_response)).decode("utf-8")
        assert captured["status"].startswith("500")
        assert "Something went wrong" in body
        assert "boom-from-wsgi" not in body
    finally:
        wsgi_module.todo_app = saved_app
        app_module._current_app = saved_current


# ----------------------------------------------------------------------
# Runner
# ----------------------------------------------------------------------
TESTS = [
    ("render: basics", test_render_basics),
    ("render: escaping & props", test_render_escaping_and_props),
    ("state: value / listeners", test_state),
    ("events: registry lifecycle", test_event_registry),
    ("todo: full flow (add/toggle/remove/clear/enter)", test_todo_flow),
    ("todo: stale event ignored", test_stale_event_is_ignored),
    ("todo: escaping & unicode", test_escaping_and_unicode),
    ("shell: styles, focus bridge, autofocus", test_page_shell_and_styles),
    ("html: tags balanced after every step", test_html_is_well_formed),
    ("app: title escaping", test_title_escaping),
    ("concurrency: 12 parallel events", test_concurrent_events),
    ("http: end-to-end", test_http_end_to_end),
    ("http: error pages", test_server_error_pages),
    ("wsgi: serverless entrypoint", test_wsgi_entrypoint),
]


def main():
    failures = []
    for name, fn in TESTS:
        reset()
        try:
            fn()
        except Exception:
            failures.append(name)
            print(f"  FAIL  {name}")
            traceback.print_exc()
        else:
            print(f"  PASS  {name}")
    print(f"\n{len(TESTS) - len(failures)}/{len(TESTS)} tests passed")
    if failures:
        print("failed: " + ", ".join(failures))
        sys.exit(1)


if __name__ == "__main__":
    main()
