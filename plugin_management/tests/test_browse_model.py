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
