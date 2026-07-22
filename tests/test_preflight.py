from council import preflight


def test_manual_mode_warns_per_profile():
    modes = {"sophie": "manual", "mia": "yolo", "noah": "manual"}
    w = preflight.warnings_for("sophie", ["mia", "noah"],
                               approval_mode_fn=lambda p: modes[p],
                               running_profiles=["*"])
    joined = "\n".join(w)
    assert "sophie" in joined and "noah" in joined
    assert "mia" not in joined            # yolo is fine


def test_no_gateway_warns():
    w = preflight.warnings_for("sophie", ["mia"],
                               approval_mode_fn=lambda p: "yolo",
                               running_profiles=[])
    assert any("게이트웨이" in x for x in w)


def test_all_auto_and_gateway_up_is_clean():
    w = preflight.warnings_for("sophie", ["mia"],
                               approval_mode_fn=lambda p: "yolo",
                               running_profiles=["mia"])
    assert w == []


def test_doctor_checks_all_pass():
    checks = preflight.doctor_checks(
        enabled_fn=lambda: True, gateway_fn=lambda: True,
        assignees_fn=lambda: True, home_writable_fn=lambda: True)
    assert [c[0] for c in checks] == ["plugin enabled", "gateway running",
                                      "kanban reachable", "registry writable"]
    assert all(ok for _, ok, _ in checks)


def test_doctor_check_reports_failure_without_raising():
    checks = preflight.doctor_checks(
        enabled_fn=lambda: False,
        gateway_fn=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        assignees_fn=lambda: True, home_writable_fn=lambda: True)
    d = dict((n, ok) for n, ok, _ in checks)
    assert d["plugin enabled"] is False
    assert d["gateway running"] is False        # exception → not ok, no crash


def test_is_runaway_boundary():
    from council import preflight as pf
    assert pf.card_cap(2, 5) == 24
    assert pf.is_runaway(25, 24, final=False) is True
    assert pf.is_runaway(24, 24, final=False) is False
    assert pf.is_runaway(999, 24, final=True) is False    # done meetings never runaway
