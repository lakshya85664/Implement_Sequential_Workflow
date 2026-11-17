
import json

import runbook


def test_evidence_inventory_detects_existing_files(tmp_path, monkeypatch):
    evidence_file = tmp_path / "task1.json"
    evidence_file.write_text(
        json.dumps({"status": "completed"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        runbook,
        "EVIDENCE_FILES",
        {"task1": evidence_file},
    )

    inventory = runbook.generate_evidence_inventory()

    assert inventory["total_expected_files"] == 1
    assert inventory["existing_files"] == 1
    assert inventory["valid_json_files"] == 1
    assert inventory["complete"] is True


def test_evidence_inventory_detects_missing_file(tmp_path, monkeypatch):
    missing_file = tmp_path / "missing.json"

    monkeypatch.setattr(
        runbook,
        "EVIDENCE_FILES",
        {"missing": missing_file},
    )

    inventory = runbook.generate_evidence_inventory()

    assert inventory["existing_files"] == 0
    assert inventory["complete"] is False
    assert inventory["missing_files"] == ["missing"]


def test_evidence_inventory_detects_invalid_json(tmp_path, monkeypatch):
    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text("{invalid json", encoding="utf-8")

    monkeypatch.setattr(
        runbook,
        "EVIDENCE_FILES",
        {"invalid": invalid_file},
    )

    inventory = runbook.generate_evidence_inventory()

    assert inventory["existing_files"] == 1
    assert inventory["valid_json_files"] == 0
    assert inventory["complete"] is False
    assert inventory["invalid_files"] == ["invalid"]


def test_runbook_contains_execution_instructions():
    content = runbook.build_runbook()

    assert "python orchestrator.py" in content
    assert "python reliability.py" in content
    assert "python adapters.py" in content
    assert "python -m pytest -v" in content


def test_runbook_documents_failure_recovery():
    content = runbook.build_runbook()

    assert "Transient service failure" in content
    assert "Permanent failure" in content
    assert "Malformed response" in content
    assert "Recovery checklist" in content


def test_runbook_documents_replay_safety():
    content = runbook.build_runbook()

    assert "Idempotency" in content
    assert "idempotency key" in content.lower()
    assert "duplicate" in content.lower()


def test_report_generation_creates_all_documents(tmp_path, monkeypatch):
    output_dir = tmp_path / "outputs"
    report_dir = tmp_path / "reports"
    trace_dir = tmp_path / "traces"

    output_dir.mkdir()
    report_dir.mkdir()
    trace_dir.mkdir()

    evidence_files = {}

    for name in runbook.EVIDENCE_FILES:
        path = tmp_path / f"{name}.json"
        path.write_text(
            json.dumps({"metrics": {"task_successes": 4}}),
            encoding="utf-8",
        )
        evidence_files[name] = path

    monkeypatch.setattr(runbook, "BASE_DIR", tmp_path)
    monkeypatch.setattr(runbook, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(runbook, "REPORT_DIR", report_dir)
    monkeypatch.setattr(runbook, "TRACE_DIR", trace_dir)
    monkeypatch.setattr(runbook, "EVIDENCE_FILES", evidence_files)
    monkeypatch.setattr(
        runbook,
        "RUNBOOK_FILE",
        report_dir / "OPERATOR_RUNBOOK.md",
    )
    monkeypatch.setattr(
        runbook,
        "EVIDENCE_FILE",
        report_dir / "evidence_report.json",
    )
    monkeypatch.setattr(
        runbook,
        "SUMMARY_FILE",
        output_dir / "task5_operator_report.json",
    )

    report = runbook.generate_reports()

    assert report["assessment_status"] == "evidence_complete"
    assert report["evidence_inventory"]["valid_json_files"] == 6

    assert (report_dir / "OPERATOR_RUNBOOK.md").exists()
    assert (report_dir / "evidence_report.json").exists()
    assert (output_dir / "task5_operator_report.json").exists()


def test_report_marks_incomplete_evidence(tmp_path, monkeypatch):
    output_dir = tmp_path / "outputs"
    report_dir = tmp_path / "reports"
    trace_dir = tmp_path / "traces"

    output_dir.mkdir()
    report_dir.mkdir()
    trace_dir.mkdir()

    missing_files = {
        name: tmp_path / f"missing_{name}.json"
        for name in runbook.EVIDENCE_FILES
    }

    monkeypatch.setattr(runbook, "BASE_DIR", tmp_path)
    monkeypatch.setattr(runbook, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(runbook, "REPORT_DIR", report_dir)
    monkeypatch.setattr(runbook, "TRACE_DIR", trace_dir)
    monkeypatch.setattr(runbook, "EVIDENCE_FILES", missing_files)
    monkeypatch.setattr(
        runbook,
        "RUNBOOK_FILE",
        report_dir / "OPERATOR_RUNBOOK.md",
    )
    monkeypatch.setattr(
        runbook,
        "EVIDENCE_FILE",
        report_dir / "evidence_report.json",
    )
    monkeypatch.setattr(
        runbook,
        "SUMMARY_FILE",
        output_dir / "task5_operator_report.json",
    )

    report = runbook.generate_reports()

    assert report["assessment_status"] == "evidence_incomplete"
    assert report["evidence_inventory"]["complete"] is False
    assert len(report["evidence_inventory"]["missing_files"]) == 6
