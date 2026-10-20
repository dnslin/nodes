import json

import pytest

from nodes import browser as app


class StateTab:
    def __init__(self, frame=None):
        self.frame = frame

    def run_js(self, script):
        return json.dumps(
            {
                "ready": True,
                "hasApi": True,
                "hasInput": True,
                "hasIframe": False,
                "tokenLen": 0,
                "token": "",
            }
        )

    def ele(self, selector, timeout):
        return self.frame


def test_state_detects_closed_shadow_iframe_through_browser_library():
    state = app._read_state(StateTab(frame=object()))
    assert state["hasIframe"] is True


def test_state_reports_browser_error_instead_of_converting_to_missing_widget():
    tab = StateTab()

    def disconnected(script):
        raise RuntimeError("browser disconnected")

    tab.run_js = disconnected
    with pytest.raises(RuntimeError, match="browser disconnected"):
        app._read_state(tab)


def test_state_reports_javascript_error_instead_of_waiting_until_timeout():
    tab = StateTab()
    tab.run_js = lambda script: json.dumps({"err": "page state unavailable"})
    with pytest.raises(RuntimeError, match="page state unavailable"):
        app._read_state(tab)


@pytest.fixture
def browser_fixture(monkeypatch):
    import DrissionPage


    tab = StateTab()
    tab.get = lambda url: None
    closed = []

    class Browser:
        latest_tab = tab

        def quit(self):
            closed.append(True)

    class Clock:
        current = 0

        def monotonic(self):
            self.current += 0.1
            return self.current

    monkeypatch.setattr(DrissionPage, "Chromium", lambda options: Browser())
    monkeypatch.setattr(app, "browser_options", lambda *args: object())
    monkeypatch.setattr(app.time, "monotonic", Clock().monotonic)
    monkeypatch.setattr(app.time, "sleep", lambda delay: None)
    return tab, closed


def run_solver():
    return app.solve_turnstile(
        timeout=2, config={"browser_path": "", "turnstile_extension_path": ""}
    )


def test_missing_native_widget_is_not_replaced_and_timeout_reports_actual_state(browser_fixture):
    tab, closed = browser_fixture
    original = tab.run_js

    def scripts(script):
        assert "turnstile.render(" not in script, "Do not create a duplicate widget"
        return original(script)

    tab.run_js = scripts
    with pytest.raises(TimeoutError, match="等待站点原生验证 iframe.*hasIframe=False"):
        run_solver()
    assert closed == [True]


def test_unknown_browser_failure_is_not_swallowed_and_browser_closes(browser_fixture):
    tab, closed = browser_fixture

    def fail(script):
        raise RuntimeError("original browser failure")

    tab.run_js = fail
    with pytest.raises(RuntimeError, match="original browser failure"):
        run_solver()
    assert closed == [True]


def test_detached_page_is_relocated_and_can_return_token(browser_fixture):
    from DrissionPage.errors import ElementLostError

    tab, closed = browser_fixture
    state = tab.run_js(app._STATE_JS)
    states = iter(
        [
            ElementLostError("frame refreshed"),
            state,
            json.dumps(
                {
                    "ready": True,
                    "hasApi": True,
                    "hasInput": True,
                    "tokenLen": 100,
                    "token": "x" * 100,
                }
            ),
        ]
    )

    def scripts(script):
        if script == app._FILL_JS:
            return "filled"
        value = next(states)
        if isinstance(value, Exception):
            raise value
        return value

    tab.run_js = scripts
    assert run_solver() == "x" * 100
    assert closed == [True]
