"""Tests for BrowsePluginsModel fetch/fallback and row building."""
from plugin_management import browse_model, package_installer


def test_fetch_data_success(monkeypatch):
    pkgs = [{"name": "a", "version": "1.0"}]
    monkeypatch.setattr(package_installer, "search_channel", lambda url: pkgs)
    model = browse_model.BrowsePluginsModel()
    data, stale = model.fetch_data()
    assert data == pkgs
    assert stale is False


def test_fetch_data_falls_back_to_cache(monkeypatch):
    def boom(url):
        raise package_installer.InstallError("offline")
    monkeypatch.setattr(package_installer, "search_channel", boom)
    monkeypatch.setattr(package_installer, "read_cached_index",
                        lambda: [{"name": "a", "version": "1.0"}])
    model = browse_model.BrowsePluginsModel()
    data, stale = model.fetch_data()
    assert data[0]["name"] == "a"
    assert stale is True


def test_set_packages_dedupes_to_latest():
    model = browse_model.BrowsePluginsModel()
    model.set_packages(
        [{"name": "a", "version": "0.1.0"}, {"name": "a", "version": "0.2.0"}],
        False)
    assert len(model.packages) == 1
    assert model.packages[0].version == "0.2.0"
    assert model.stale is False


def test_drop_installed_removes_the_row_without_refetching(monkeypatch):
    """After an install the channel offers exactly what it did before — only
    the installed set changed. Rebuilding the rows must not re-fetch."""
    fetches = []
    monkeypatch.setattr(package_installer, "search_channel",
                        lambda url: fetches.append(url))
    monkeypatch.setattr(package_installer, "installed_plugin_dists", lambda: {})
    model = browse_model.BrowsePluginsModel()
    model.set_packages([{"name": "a", "version": "1.0"},
                        {"name": "b", "version": "2.0"}], False)
    assert [p.name for p in model.packages] == ["a", "b"]

    monkeypatch.setattr(package_installer, "installed_plugin_dists",
                        lambda: {"a": "1.0"})
    model.drop_installed()

    assert [p.name for p in model.packages] == ["b"]
    assert fetches == []               # no network round-trip


def test_drop_installed_clears_a_selection_whose_row_is_gone(monkeypatch):
    """The details pane must not keep describing a package that just left."""
    monkeypatch.setattr(package_installer, "installed_plugin_dists", lambda: {})
    model = browse_model.BrowsePluginsModel()
    model.set_packages([{"name": "a", "version": "1.0"}], False)
    model.selected = model.packages[0]
    assert model.details_text

    monkeypatch.setattr(package_installer, "installed_plugin_dists",
                        lambda: {"a": "1.0"})
    model.drop_installed()

    assert model.selected is None
    assert model.details_text == ""


def test_drop_installed_keeps_an_unaffected_selection(monkeypatch):
    """Installing one package must not clear a selection on a different row."""
    monkeypatch.setattr(package_installer, "installed_plugin_dists", lambda: {})
    model = browse_model.BrowsePluginsModel()
    model.set_packages([{"name": "a", "version": "1.0"},
                        {"name": "b", "version": "2.0"}], False)
    model.selected = [p for p in model.packages if p.name == "b"][0]

    monkeypatch.setattr(package_installer, "installed_plugin_dists",
                        lambda: {"a": "1.0"})
    model.drop_installed()

    assert model.selected is not None
    assert model.selected.name == "b"
