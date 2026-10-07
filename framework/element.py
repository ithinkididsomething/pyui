"""PyUI element classes - the nodes of the component tree.

A UI described with PyUI is just a tree of these small objects.  Every node
knows three things:

    tag      - which HTML tag it becomes (e.g. "div", "button", "input")
    props    - its properties (rendered as HTML attributes)
    children - nested nodes

Example:

    Column(
        Text("Hello"),
        Button("Click", on_click=handler),
    )

builds this tree:

    Column
    ├── Text("Hello")
    └── Button  props={"on_click": handler}

renderer.py walks this tree and turns it into HTML.  Nothing here talks to
the browser, the network, or state - components are plain data.
"""


class Text:
    """A piece of text.

    With no extra props it renders as plain (escaped) text.  If you pass
    props, e.g. Text("Done", style="color:gray"), it renders as a <span>
    so the props have somewhere to live.
    """

    def __init__(self, text, **props):
        self.text = text
        self.props = props

    def __repr__(self):
        return f"Text({self.text!r})"


def _normalize_children(children):
    """Make children a flat list of Text/Element nodes.

    Lets developers be sloppy in useful ways:
      * pass a list of children instead of unpacking it with *
      * pass raw strings (they become Text nodes)
      * pass None / False (they disappear) - handy for conditions:
        Column(Text("Hi"), condition and Text("only if true"))
    """
    out = []
    for child in children:
        if child is None or child is False:
            continue
        if isinstance(child, (list, tuple)):
            out.extend(_normalize_children(child))
        elif isinstance(child, str):
            out.append(Text(child))
        elif isinstance(child, (Text, Element)):
            out.append(child)
        else:
            raise TypeError(
                f"PyUI child must be a component, Text, str, list or None, "
                f"got {type(child).__name__}. Did you mean Text({child!r})?"
            )
    return out


class Element:
    """Generic element. Renders as a <div> unless the class says otherwise."""

    tag = "div"
    default_style = None  # Column/Row override this with flexbox styles

    def __init__(self, *children, **props):
        self.children = _normalize_children(children)
        if self.default_style:
            # Keep the default layout style, let user props extend it.
            props["style"] = self.default_style + props.get("style", "")
        self.props = props

    def __repr__(self):
        return f"{type(self).__name__}(children={self.children!r}, props={self.props!r})"


class Button(Element):
    """A clickable button.

    `on_click` (and optionally `on_enter`) must be a Python function.  The
    renderer registers it with events.py and puts a small id in the HTML;
    when the browser reports that id the function is called.
    """

    tag = "button"

    def __init__(self, label, on_click=None, on_enter=None, **props):
        if on_click is not None:
            props["on_click"] = on_click
        if on_enter is not None:
            props["on_enter"] = on_enter
        # `label` may be a plain string (becomes Text) or any component.
        super().__init__(label, **props)


class Input(Element):
    """A single-line text field (a void element, it has no children).

    Pass `value=some_state` where some_state is a State object to keep the
    field in sync with Python: the rendered value comes from the state, and
    on every event the browser sends the field contents back so the state
    is updated before your callback runs.

    Pass `on_enter=some_function` to run a callback when the user presses
    Enter in the field.
    """

    tag = "input"

    def __init__(self, value="", placeholder="", on_enter=None, **props):
        props.setdefault("value", value)
        if placeholder:
            props.setdefault("placeholder", placeholder)
        if on_enter is not None:
            props["on_enter"] = on_enter
        super().__init__(**props)


class Column(Element):
    """Children stacked vertically."""

    default_style = "display:flex;flex-direction:column;gap:8px;"


class Row(Element):
    """Children laid out horizontally."""

    default_style = (
        "display:flex;flex-direction:row;gap:8px;"
        "align-items:center;flex-wrap:wrap;"
    )
