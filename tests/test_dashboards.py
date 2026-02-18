import json

EXPECTED_DASHBOARDS = {
    "01-overview.json": "oura-overview",
    "02-sleep.json": "oura-sleep",
    "03-readiness.json": "oura-readiness",
    "04-activity.json": "oura-activity",
    "05-body.json": "oura-body",
}

DATASOURCE_UID = "oura-pg"


class TestDashboardFiles:
    def test_all_dashboards_exist(self, dashboard_files):
        names = {f.name for f in dashboard_files}
        for expected in EXPECTED_DASHBOARDS:
            assert expected in names, f"Missing dashboard: {expected}"

    def test_valid_json(self, dashboard_files):
        for f in dashboard_files:
            data = json.loads(f.read_text())
            assert isinstance(data, dict), f"{f.name} root is not an object"


class TestDashboardStructure:
    def test_required_fields(self, loaded_dashboards, dashboard_files):
        for dash, f in zip(loaded_dashboards, dashboard_files):
            assert "uid" in dash, f"{f.name} missing uid"
            assert "title" in dash, f"{f.name} missing title"
            assert "panels" in dash, f"{f.name} missing panels"
            assert isinstance(dash["panels"], list), f"{f.name} panels is not a list"
            assert len(dash["panels"]) > 0, f"{f.name} has no panels"

    def test_unique_uids(self, loaded_dashboards):
        uids = [d["uid"] for d in loaded_dashboards]
        assert len(uids) == len(set(uids)), f"Duplicate UIDs found: {uids}"

    def test_expected_uids(self, loaded_dashboards):
        uids = {d["uid"] for d in loaded_dashboards}
        for expected_uid in EXPECTED_DASHBOARDS.values():
            assert expected_uid in uids, f"Missing UID: {expected_uid}"


class TestDatasourceRefs:
    def test_panel_datasources(self, loaded_dashboards, dashboard_files):
        for dash, f in zip(loaded_dashboards, dashboard_files):
            for panel in dash["panels"]:
                ds = panel.get("datasource")
                if ds and isinstance(ds, dict) and ds.get("uid"):
                    assert ds["uid"] == DATASOURCE_UID, (
                        f"{f.name} panel '{panel.get('title')}' has wrong datasource UID: {ds['uid']}"
                    )

    def test_target_datasources(self, loaded_dashboards, dashboard_files):
        for dash, f in zip(loaded_dashboards, dashboard_files):
            for panel in dash["panels"]:
                for target in panel.get("targets", []):
                    ds = target.get("datasource")
                    if ds and isinstance(ds, dict) and ds.get("uid"):
                        assert ds["uid"] == DATASOURCE_UID, (
                            f"{f.name} panel '{panel.get('title')}' target has wrong datasource: {ds['uid']}"
                        )


class TestPanelIntegrity:
    def test_all_panels_have_titles(self, loaded_dashboards, dashboard_files):
        for dash, f in zip(loaded_dashboards, dashboard_files):
            for panel in dash["panels"]:
                if panel.get("type") != "row":
                    assert panel.get("title"), f"{f.name} panel id={panel.get('id')} has no title"

    def test_all_panels_have_ids(self, loaded_dashboards, dashboard_files):
        for dash, f in zip(loaded_dashboards, dashboard_files):
            ids = []
            for panel in dash["panels"]:
                assert "id" in panel, f"{f.name} has panel without id"
                ids.append(panel["id"])
            assert len(ids) == len(set(ids)), f"{f.name} has duplicate panel IDs"

    def test_panel_count(self, loaded_dashboards):
        total = sum(len(d["panels"]) for d in loaded_dashboards)
        assert total == 70, f"Expected 70 total panels, got {total}"
