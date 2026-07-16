"""finish_change picks the right ending: a plain confirmation when the change
is already live, the relaunch offer when it is not."""
from plugin_management import relaunch


def test_finish_change_informs_when_already_live(monkeypatch):
    seen = {}
    monkeypatch.setattr(relaunch, "information",
                        lambda **kw: seen.update(kw))
    monkeypatch.setattr(relaunch, "confirm_and_relaunch",
                        lambda *a: seen.update(relaunched=True))

    relaunch.finish_change(None, "Installed and enabled <b>X</b>.", True)

    assert seen["message"] == "Installed and enabled <b>X</b>."
    assert "relaunched" not in seen


def test_finish_change_offers_relaunch_when_not_live(monkeypatch):
    seen = {}
    monkeypatch.setattr(relaunch, "information",
                        lambda **kw: seen.update(informed=True))
    monkeypatch.setattr(relaunch, "confirm_and_relaunch",
                        lambda task, msg: seen.update(msg=msg))

    relaunch.finish_change(None, "Installed <b>X</b>.", False)

    assert seen["msg"] == "Installed <b>X</b>."
    assert "informed" not in seen
