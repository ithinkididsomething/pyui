"""The PyUI application - renders pages and turns browser events into Python calls.

An App has two jobs:

1. render_page() / render_content()
       Call your root function, walk the component tree it returns, and
       produce HTML.  Called once when the page loads and again after every
       event.

2. handle_event(payload)
       Run when the browser reports an event.  It
         a. looks up the Python callback for the id and calls it,
         b. copies field contents from the browser into their States first,
         c. re-renders the whole UI and returns the fresh HTML,
       which the browser drops into <div id="pyui-app">.

The page also carries a tiny auto-generated script (see PAGE below) that
does nothing but POST events to /event and swap the HTML - the developer
never writes any JavaScript.  The script also preserves focus and cursor
position in input fields across re-renders, so typing stays pleasant.
"""

import html as html_module
import threading
from string import Template

from . import events
from .renderer import render
from .state import add_change_listener, sync_states

# One lock serialises render/event handling: the handler registry and the
# States are shared, so two requests must never interleave.
_lock = threading.RLock()

# The running App (State.set() uses this to mark the UI dirty).
_current_app = None


def _mark_ui_dirty(state):
    if _current_app is not None:
        _current_app.dirty = True


# Wire State.set() -> "this app needs a re-render".
add_change_listener(_mark_ui_dirty)


class App:
    """Wraps a root render function into a running browser application.

        def counter():
            return Column(...)
        app = App(counter, title="Counter", styles=".x { color: red }")
    """

    def __init__(self, root, title="PyUI App", styles=""):
        self.root = root                    # zero-arg function -> component tree
        self.title = html_module.escape(str(title))
        self.styles = styles                # extra CSS injected after the base CSS
        self.dirty = False                  # set by State.set(), cleared by rendering
        global _current_app
        _current_app = self

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def render_content(self):
        """Build the component tree and return its HTML (page body only)."""
        with _lock:
            events.begin_render()      # fresh callback registry per render
            html = render(self.root())
            self.dirty = False
            return html

    def render_page(self):
        """Return the complete HTML document for the browser."""
        return PAGE.safe_substitute(
            title=self.title,
            styles=self.styles,
            content=self.render_content(),
        )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def handle_event(self, payload):
        """Handle {handler: id, inputs: {state_id: value}} from the browser.

        Returns the freshly rendered HTML for <div id="pyui-app">.
        """
        with _lock:
            # Find the callback first.  An id from an *older* render (a click
            # that raced with another re-render) matches nothing - in that
            # case we deliberately ignore the whole event, including its
            # input snapshot, so a stale request cannot undo newer state.
            callback = events.get(payload.get("handler"))

            if callback is not None:
                # a. The browser sent the current contents of every input
                #    field bound to a State - copy them in *before* the
                #    callback runs so it can read them.
                inputs = payload.get("inputs") or {}
                if isinstance(inputs, dict):
                    sync_states(inputs)

                # b. Run the Python callback the user clicked/pressed.
                callback()

            # c. Full re-render - no diffing, just a brand new HTML string.
            return self.render_content()


# ----------------------------------------------------------------------
# The HTML shell: base styles, app-specific styles ($styles), the app
# container, and the tiny auto-generated event bridge.
# ----------------------------------------------------------------------
PAGE = Template("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; padding: 32px 16px;
    background: #f5f6f8;
    color: #1f2937;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, sans-serif;
    line-height: 1.45;
  }
  #pyui-app {
    max-width: 640px; margin: 0 auto; background: #fff;
    border: 1px solid #e5e7eb; border-radius: 16px; padding: 24px;
    box-shadow: 0 10px 30px -12px rgba(15, 23, 42, 0.18),
                0 2px 6px rgba(15, 23, 42, 0.05);
    animation: pyui-in 0.45s cubic-bezier(0.2, 0.7, 0.3, 1) both;
  }
  @keyframes pyui-in {
    from { opacity: 0; transform: translateY(14px); }
    to   { opacity: 1; transform: none; }
  }
  @media (prefers-reduced-motion: reduce) {
    #pyui-app { animation: none; }
  }
  button {
    font: inherit; border: 1px solid #d1d5db; background: #fff; color: #1f2937;
    border-radius: 9px; padding: 8px 14px; font-size: 14px; cursor: pointer;
    transition: background .12s ease, border-color .12s ease,
                color .12s ease, box-shadow .12s ease;
  }
  button:hover { background: #f9fafb; border-color: #9ca3af; }
  button:active { transform: translateY(1px); }
  button:focus-visible { outline: 2px solid #6366f1; outline-offset: 2px; }
  button:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
  input {
    font: inherit; border: 1px solid #d1d5db; border-radius: 9px;
    padding: 9px 12px; font-size: 14px; color: #111827; background: #fff;
    transition: border-color .12s ease, box-shadow .12s ease;
  }
  input::placeholder { color: #9ca3af; }
  input:focus { outline: none; border-color: #6366f1;
                box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.18); }
</style>
<style>
$styles
</style>
</head>
<body>
<div id="pyui-app">$content</div>
<noscript><p>Please enable JavaScript to use this app.</p></noscript>
<script>
(function () {
  var pendingExt = null;
  var popBusy = false;

  function reduced() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function selectionOf(el) {
    try { return [el.selectionStart, el.selectionEnd]; } catch (e) { return null; }
  }

  function armPop(from) {
    if (pendingExt || popBusy || reduced()) return;
    var bar = from.closest("[data-pyui-pop]");
    if (!bar) return;
    var input = bar.querySelector("input");
    if (!input) return;
    var h = input.getBoundingClientRect().height;
    bar.style.alignItems = "flex-start";
    bar.style.position = "relative";
    bar.style.zIndex = "3";
    pendingExt = {
      bar: bar,
      h: h,
      t0: performance.now(),
      anim: input.animate(
        [
          { height: h + "px", marginBottom: "0px" },
          { height: h * 2 + "px", marginBottom: -h + "px" }
        ],
        { duration: 200, easing: "cubic-bezier(0.3, 0.7, 0.3, 1)", fill: "forwards" }
      )
    };
  }

  function overlay(node, rect, height, z) {
    node.style.position = "fixed";
    node.style.left = rect.left + "px";
    node.style.top = rect.top + "px";
    node.style.width = rect.width + "px";
    node.style.height = height + "px";
    node.style.margin = "0";
    node.style.zIndex = z;
    node.style.pointerEvents = "none";
    document.body.appendChild(node);
    return node;
  }

  function doSwap(html, keep) {
    document.getElementById("pyui-app").innerHTML = html;
    var next = null;
    if (keep) {
      next = document.querySelector('#pyui-app [data-pyui-input="' + keep.id + '"]');
    }
    if (!next) {
      next = document.querySelector("#pyui-app [autofocus]");
    }
    if (next) {
      next.focus();
      try {
        if (keep && keep.sel) next.setSelectionRange(keep.sel[0], keep.sel[1]);
        else next.setSelectionRange(next.value.length, next.value.length);
      } catch (e) {}
    }
  }

  function popNew(oldKeys) {
    if (reduced()) return;
    document.querySelectorAll("#pyui-app [data-pyui-key]").forEach(function (el) {
      if (oldKeys[el.getAttribute("data-pyui-key")]) return;
      el.animate(
        [
          { opacity: 0, transform: "scale(0.6)" },
          { opacity: 1, transform: "scale(1)" }
        ],
        { duration: 280, easing: "cubic-bezier(0.2, 0.8, 0.3, 1)" }
      );
    });
  }

  function releaseExt(ext) {
    if (!ext) return;
    ext.anim.cancel();
    ext.bar.style.alignItems = "";
    ext.bar.style.position = "";
    ext.bar.style.zIndex = "";
  }

  function swap(html) {
    var oldKeys = {};
    document.querySelectorAll("#pyui-app [data-pyui-key]").forEach(function (el) {
      oldKeys[el.getAttribute("data-pyui-key")] = 1;
    });
    var active = document.activeElement;
    var keep = null;
    if (active && active.hasAttribute && active.hasAttribute("data-pyui-input")) {
      keep = { id: active.getAttribute("data-pyui-input"), sel: selectionOf(active) };
    }

    var ext = pendingExt;
    pendingExt = null;
    var barKey = ext ? ext.bar.getAttribute("data-pyui-key") : null;
    var split =
      ext && barKey && !reduced() && !popBusy &&
      html.indexOf('data-pyui-from="' + barKey + '"') !== -1;

    if (!split) {
      releaseExt(ext);
      doSwap(html, keep);
      popNew(oldKeys);
      return;
    }

    // Wait out the extend phase, then run the break-apart choreography.
    popBusy = true;
    var wait = ext.t0 + 210 - performance.now();
    setTimeout(function () { begin(); }, wait > 0 ? wait : 0);

    function begin() {
      var bar = ext.bar;
      if (!bar.isConnected) { popBusy = false; return; }

      var rect = bar.getBoundingClientRect();
      var input = bar.querySelector("input");
      var text = input ? input.value : "";
      if (input) input.setAttribute("value", text);
      ext.anim.cancel();
      if (input) {
        input.style.height = ext.h * 2 + "px";
        input.style.marginBottom = "0px";
      }

      var topGh = overlay(bar.cloneNode(true), rect, ext.h * 2, 41);
      var botGh = overlay(bar.cloneNode(true), rect, ext.h * 2, 41);
      topGh.style.clipPath = "inset(0 0 38% 0)";
      botGh.style.clipPath = "inset(62% 0 0 0)";

      var span = document.createElement("span");
      span.textContent = text;
      span.style.cssText =
        "position:absolute;left:48px;right:12px;top:62%;height:38%;" +
        "display:flex;align-items:center;font-size:.95rem;color:#1f2937;" +
        "white-space:nowrap;overflow:hidden;text-overflow:ellipsis;";
      botGh.appendChild(span);

      doSwap(html, keep);

      var el = null;
      document.querySelectorAll("#pyui-app [data-pyui-key]").forEach(function (n) {
        if (!oldKeys[n.getAttribute("data-pyui-key")]) el = n;
      });
      if (!el) {
        topGh.remove(); botGh.remove(); popBusy = false; return;
      }
      el.style.opacity = "0";

      var eR = el.getBoundingClientRect();
      var bR = botGh.getBoundingClientRect();
      var dx = eR.left + eR.width / 2 - (bR.left + bR.width / 2);
      var dy = eR.top + eR.height / 2 - (bR.top + bR.height / 2);

      topGh.animate(
        [
          { transform: "translate(0px, 0px)", opacity: 1 },
          { transform: "translate(0px, -8px)", opacity: 1, offset: 0.4,
            easing: "cubic-bezier(0.2, 0.8, 0.3, 1)" },
          { transform: "translate(0px, -5px)", opacity: 0 }
        ],
        { duration: 320, fill: "forwards" }
      );

      var travel = botGh.animate(
        [
          { transform: "translate(0px, 0px)", opacity: 1,
            easing: "cubic-bezier(0.2, 0.9, 0.4, 1)" },
          { transform: "translate(0px, 10px)", opacity: 1, offset: 0.12,
            easing: "cubic-bezier(0.2, 0.75, 0.3, 1)" },
          { transform: "translate(" + dx * 0.9 + "px, " +
              (10 + (dy - 10) * 0.95) + "px)",
            opacity: 1, offset: 0.72,
            easing: "cubic-bezier(0.4, 0, 0.6, 1)" },
          { transform: "translate(" + dx + "px, " + dy + "px)", opacity: 0 }
        ],
        { duration: 520, fill: "forwards" }
      );

      var reveal = el.animate(
        [
          { opacity: 0, transform: "scale(1.03)" },
          { opacity: 1, transform: "scale(1)" }
        ],
        { duration: 240, delay: 260,
          easing: "cubic-bezier(0.2, 0.8, 0.3, 1)", fill: "both" }
      );

      reveal.finished
        .then(function () { reveal.cancel(); el.style.opacity = ""; })
        .catch(function () {});
      travel.finished
        .then(function () { botGh.remove(); topGh.remove(); popBusy = false; })
        .catch(function () { popBusy = false; });
    }
  }

  function postEvent(handler) {
    var inputs = {};
    document.querySelectorAll("[data-pyui-input]").forEach(function (el) {
      inputs[el.getAttribute("data-pyui-input")] = el.value;
    });
    fetch("/event", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ handler: handler, inputs: inputs })
    })
      .then(function (response) { return response.text(); })
      .then(swap)
      .catch(function (err) { console.error("PyUI: event request failed", err); });
  }

  document.addEventListener("click", function (ev) {
    var el = ev.target.closest("[data-pyui-click]");
    if (!el) return;
    ev.preventDefault();
    armPop(el);
    postEvent(el.getAttribute("data-pyui-click"));
  });

  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "Enter") return;
    var el = ev.target.closest("[data-pyui-enter]");
    if (!el) return;
    ev.preventDefault();
    armPop(el);
    postEvent(el.getAttribute("data-pyui-enter"));
  });
})();
</script>
</body>
</html>
""")
