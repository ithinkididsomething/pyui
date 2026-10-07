"""Todo list application - built ONLY with PyUI components.

No HTML strings and no JavaScript appear anywhere in this file: the UI is
described as a Python component tree, and PyUI renders it for the browser.
The CSS at the top is passed to App(styles=...) purely for presentation.
"""

from framework import App, Button, Column, Input, Row, State, Text

# ----------------------------------------------------------------------
# Presentation (plain CSS, injected into the page by App)
# ----------------------------------------------------------------------
TODO_CSS = """
.todo-head { justify-content: space-between; }
.todo-title { font-size: 1.3rem; font-weight: 700; color: #111827; }
.badge { background: #eef2ff; color: #4f46e5; font-size: 0.78rem;
         font-weight: 600; padding: 5px 12px; border-radius: 999px;
         white-space: nowrap; }
.new-row { gap: 8px; }
.new-input { flex: 1; min-width: 180px; }
.btn-primary { background:
                 linear-gradient(180deg, rgba(255,255,255,.32) 0%,
                                         rgba(255,255,255,0) 55%),
                 linear-gradient(135deg, rgba(99,102,241,.75) 0%,
                                         rgba(79,70,229,.6) 100%);
               backdrop-filter: blur(12px);
               -webkit-backdrop-filter: blur(12px);
               border: 1px solid rgba(255,255,255,.45);
               color: #fff; font-weight: 600; padding: 9px 16px;
               box-shadow: 0 8px 20px -8px rgba(79,70,229,.55),
                           inset 0 1px 0 rgba(255,255,255,.5); }
.btn-primary:hover { background:
                       linear-gradient(180deg, rgba(255,255,255,.4) 0%,
                                               rgba(255,255,255,0) 55%),
                       linear-gradient(135deg, rgba(99,102,241,.88) 0%,
                                               rgba(79,70,229,.72) 100%);
                     border-color: rgba(255,255,255,.7);
                     box-shadow: 0 10px 24px -8px rgba(79,70,229,.6),
                                 inset 0 1px 0 rgba(255,255,255,.6); }
.btn-primary:active { transform: scale(.96); }
.task { border: 1px solid #e5e7eb; border-radius: 10px; background: #f9fafb;
        padding: 8px 10px;
        transition: border-color .12s ease, background .12s ease; }
.task:hover { border-color: #c7d2fe; background: #fff; }
.task-title { flex: 1; font-size: 0.95rem; color: #1f2937;
              overflow-wrap: anywhere; }
.task-done { text-decoration: line-through; color: #9ca3af; }
.toggle { width: 30px; height: 30px; padding: 0; border-radius: 50%;
          display: inline-flex; align-items: center; justify-content: center;
          font-size: 15px; border-color: #c7d2fe; color: #6366f1; }
.toggle:hover { background: #eef2ff; }
.toggle-on { background: #10b981; border-color: #10b981; color: #fff; }
.toggle-on:hover { background: #059669; border-color: #059669; }
.btn-ghost { border-color: transparent; background: transparent;
             color: #9ca3af; padding: 6px 9px; font-size: 16px; line-height: 1; }
.btn-ghost:hover { background: #fee2e2; border-color: #fecaca; color: #dc2626; }
.empty { text-align: center; color: #9ca3af; font-size: 0.92rem;
         padding: 20px 0 8px; }
.footer { justify-content: space-between; border-top: 1px solid #f3f4f6;
          padding-top: 14px; font-size: 0.85rem; color: #6b7280; }
.footer button { font-size: 0.82rem; padding: 6px 12px; }
"""

# ----------------------------------------------------------------------
# State
# ----------------------------------------------------------------------
tasks = State([])  # list of {"title": str, "done": bool}
draft = State("")  # text currently typed into the input field


# ----------------------------------------------------------------------
# Event handlers - plain Python functions, called by the framework
# ----------------------------------------------------------------------
def add_task():
    title = draft.value.strip()
    if not title:
        return
    tasks.set(tasks.value + [{"title": title, "done": False}])
    draft.set("")  # clear the input box; re-render shows it empty


def toggle_task(index):
    updated = list(tasks.value)
    task = updated[index]
    updated[index] = {"title": task["title"], "done": not task["done"]}
    tasks.set(updated)


def remove_task(index):
    tasks.set([t for i, t in enumerate(tasks.value) if i != index])


def clear_completed():
    tasks.set([t for t in tasks.value if not t["done"]])


# ----------------------------------------------------------------------
# Components
# ----------------------------------------------------------------------
def task_row(task, index):
    # `index=index` freezes the loop variable into the lambda's default
    # argument - without it every button would act on the last index.
    done = task["done"]
    title = task["title"]
    return Row(
        Button(
            "✓" if done else "",
            class_="toggle toggle-on" if done else "toggle",
            aria_label="Mark as not done" if done else "Mark as done",
            on_click=lambda index=index: toggle_task(index),
        ),
        Text(title, class_="task-title task-done" if done else "task-title"),
        Button(
            "×",
            class_="btn-ghost",
            aria_label=f"Remove {title}",
            on_click=lambda index=index: remove_task(index),
        ),
        class_="task",
        data_pyui_key=f"task-{index}",
        data_pyui_from="typebar",
    )


def todo_app():
    items = tasks.value
    remaining = sum(1 for task in items if not task["done"])
    done_count = len(items) - remaining

    if not items:
        badge = "0 tasks"
        summary = ""
    else:
        badge = f"{len(items)} task" + ("s" if len(items) != 1 else "")
        summary = (
            "All done ✓"
            if remaining == 0
            else f"{remaining} of {len(items)} left"
        )

    return Column(
        Row(
            Text("My Todo List", class_="todo-title"),
            Text(badge, class_="badge"),
            class_="todo-head",
        ),
        Row(
            Input(
                value=draft,
                placeholder="What needs doing?",
                on_enter=add_task,
                autofocus=True,
                maxlength="120",
                class_="new-input",
            ),
            Button("Add Task", on_click=add_task, class_="btn-primary"),
            class_="new-row",
            data_pyui_key="typebar",
            data_pyui_pop=True,
        ),
        Column([task_row(task, i) for i, task in enumerate(items)])
        if items
        else Text("Nothing here yet — add your first task above.", class_="empty"),
        Row(
            Text(summary),
            Button(
                "Clear completed",
                on_click=clear_completed,
                disabled=done_count == 0,
            ),
            class_="footer",
        )
        if items
        else None,
        style="gap:18px;",
    )


# The App wraps the root function; PyUI calls it for every render.
app = App(todo_app, title="Todo", styles=TODO_CSS)
