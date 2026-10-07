"""HTML renderer - walks a PyUI component tree and produces an HTML string.

There is no virtual DOM, no diffing and no patching.  Every render starts
from the root function, builds a fresh tree, and produces a fresh chunk of
HTML.  The browser simply swaps its container's contents for whatever came
back.

    Text("Hi")                     ->  Hi
    Button("Click Me")             ->  <button>Click Me</button>
    Column(Text("Hello"), Button("Click"))
                                  ->  <div style="..."><p>Hello</p>...
                                      <button>Click</button></div>
"""

import html as html_module
import keyword

from . import events
from .element import Element, Text
from .state import State

# HTML tags that never get a closing tag (rendered as <input ...>).
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "source", "track", "wbr",
}


def render(node):
    """Render a PyUI node (or list of nodes) to an HTML string."""
    if node is None or node is False:
        return ""  # allows `Condition and Component` style children
    if isinstance(node, (list, tuple)):
        return "".join(render(child) for child in node)
    if isinstance(node, Text):
        return _render_text(node)
    if isinstance(node, Element):
        return _render_element(node)
    raise TypeError(
        f"PyUI cannot render {type(node).__name__}. "
        "Wrap plain strings in Text() and use components for structure."
    )


def _render_text(node):
    escaped = html_module.escape(str(node.text))
    attrs = _render_attrs(node.props)
    if attrs:
        # Props were supplied, so the text needs an element to carry them.
        return f"<span{attrs}>{escaped}</span>"
    return escaped


def _render_element(node):
    attrs = _render_attrs(node.props)
    if node.tag in VOID_TAGS:
        return f"<{node.tag}{attrs}>"
    children = "".join(render(child) for child in node.children)
    return f"<{node.tag}{attrs}>{children}</{node.tag}>"


def _render_attrs(props):
    """Turn a prop dict into an HTML attribute string.

    Two kinds of props never appear literally in the HTML:

    * on_click / on_enter - Python callbacks.  They are registered with
      events.py and emitted as data-pyui-click / data-pyui-enter ids so the
      tiny browser script knows which Python function to trigger.

    * value holding a State - the current value is written into the HTML,
      and data-pyui-input="<state id>" is added so the browser script can
      send all field contents back on the next event.

    Every other prop becomes a plain HTML attribute, with underscores
    mapped to dashes (aria_label -> aria-label) except where the
    underscore only escapes a Python keyword (class_ -> class).
    """
    props = dict(props)  # copy, we strip special keys out
    parts = []

    # Event callbacks -> id attributes
    for prop_name, attr_name in (
        ("on_click", "data-pyui-click"),
        ("on_enter", "data-pyui-enter"),
    ):
        callback = props.pop(prop_name, None)
        if callable(callback):
            parts.append(f' {attr_name}="{events.register(callback)}"')

    # State-backed input value -> value attribute + sync id
    value = props.get("value")
    if isinstance(value, State):
        parts.append(f' data-pyui-input="{value.id}"')
        props["value"] = value.value

    # Everything else becomes a normal HTML attribute.
    for name, val in props.items():
        if val is None or val is False:
            continue
        # Prop names that are not valid/correct HTML as-is:
        #   class_="x"      -> class="x"      (escaped Python keyword)
        #   aria_label="x"  -> aria-label="x" (underscores become dashes)
        if name.endswith("_") and keyword.iskeyword(name[:-1]):
            name = name[:-1]
        else:
            name = name.replace("_", "-")
        if val is True:
            parts.append(f" {name}")
        else:
            escaped = html_module.escape(str(val), quote=True)
            parts.append(f' {name}="{escaped}"')

    return "".join(parts)
