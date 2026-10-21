"""Two things anyone may use that belong to no single business area.

    config.py   settings: data dir, model address
    llm.py      calling models (text). The two multimodal paths are not here -
                ``editor/vision.py`` serves the editor feature, and
                ``harness/tools/imagegen.py`` is the part doing the work behind a tool;
                each follows its user.

**Only this kind of thing belongs here.** If a module can say "which business area it serves",
it should move to that area; only what cannot say so stays here. The smaller this package, the better.
"""
