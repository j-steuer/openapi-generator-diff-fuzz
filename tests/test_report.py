"""Unit tests for DiffReport."""

import tempfile
from pathlib import Path

import pytest
from requests.models import CaseInsensitiveDict

from telephuzz.evaluation.report import DiffReport
from telephuzz.http_message import HTTPMethod, Request

BASIC_REQUEST = Request(
    headers=CaseInsensitiveDict({"Test": ["test"]}),
    body=None,
    method=HTTPMethod.GET,
    path="dummytarget.org/test",
    query_parameters={},
)


def test_init(basic_request: Request) -> None:
    """Test basic init."""
    lib_id = "TestLib1"
    err_id = "Error1"

    report = DiffReport(
        library_id=lib_id,
        error_id=err_id,
        request_chain=[basic_request],
        produced_request=basic_request,
    )

    assert report.library_id == lib_id
    assert report.error_id == err_id
    assert len(report.request_chain) == 1 and report.request_chain[0] == basic_request
    assert report.request_chain[0] == report.produced_request
    assert report.detail == "", "Default detail should be empty"


def test_compare(basic_request: Request) -> None:
    """Test __hash__ and __eq__ methods."""
    report1 = DiffReport("Eq1", "Err1", [basic_request], basic_request)
    # different request chain
    report2 = DiffReport("Eq1", "Err1", [], basic_request)
    # uniqueness should cause it to be unequal
    report3 = DiffReport("Eq1", "Err1", [basic_request], basic_request, unique=False)

    assert report1 != report2
    assert report2 != report3
    assert report1 != report3

    assert len({report1, report2, report3}) == 3
    assert len({report1, report1, report2}) == 2


def test_unify_persistent(basic_request) -> None:
    """Assert that persistent is True as long as one report claims persistancy."""
    reports = {
        frozenset(
            {
                DiffReport("1", "2", request_chain=[], produced_request=basic_request),
                DiffReport("1", "2", request_chain=[], produced_request=basic_request),
                DiffReport("1", "2", request_chain=[], produced_request=basic_request),
            }
        )
    }

    unified_reports = DiffReport.unify(reports)
    assert len(unified_reports) == 1

    assert unified_reports.pop() == DiffReport(
        "1", "2", request_chain=[], produced_request=basic_request
    )


def test_unify_detail(basic_request) -> None:
    """Assert that details are concatenated."""
    reports = {
        frozenset(
            {
                DiffReport(
                    "1",
                    "2",
                    request_chain=[],
                    produced_request=basic_request,
                    detail="Detail1",
                ),
                DiffReport(
                    "1",
                    "2",
                    request_chain=[],
                    produced_request=basic_request,
                    detail="Detail2",
                ),
            }
        )
    }

    unified_reports = DiffReport.unify(reports)
    assert len(unified_reports) == 1

    unified_detail = unified_reports.pop().detail
    assert "Detail1" in unified_detail and "Detail2" in unified_detail


def test_unique_assignment(basic_request) -> None:
    """Test correct uniqueness assignment."""
    unique_report = DiffReport("1", "1", [], produced_request=basic_request)
    same_error_report1 = DiffReport("1", "2", [], produced_request=basic_request)
    same_error_report2 = DiffReport("2", "2", [], produced_request=basic_request)
    same_error_report3 = DiffReport("3", "2", [], produced_request=basic_request)
    same_error_report4 = DiffReport("4", "2", [], produced_request=basic_request)

    reports = reports = {
        frozenset({unique_report}),
        frozenset({same_error_report1}),
        frozenset({same_error_report2}),
        frozenset({same_error_report3}),
        frozenset({same_error_report4}),
    }
    result = DiffReport.unify(reports)
    assert len(result) == 5

    assert unique_report.unique
    assert not same_error_report1.unique
    assert not same_error_report2.unique
    assert not same_error_report3.unique
    assert not same_error_report4.unique


@pytest.mark.parametrize(
    ["report1", "report2"],
    [
        (
            DiffReport("1", "1", [], produced_request=BASIC_REQUEST),
            DiffReport("2", "1", [], produced_request=BASIC_REQUEST),
        ),
        (
            DiffReport("1", "1", [], produced_request=BASIC_REQUEST),
            DiffReport("1", "2", [], produced_request=BASIC_REQUEST),
        ),
    ],
    ids=["library_id", "error_id"],
)
def test_id_mismatch(report1: DiffReport, report2: DiffReport) -> None:
    """Test that unify raises if two ids within same set are not the same."""
    with pytest.raises(ValueError, match="different libraries or errors"):
        DiffReport.unify({frozenset({report1, report2})})


def test_request_chain_mismatch(basic_request: Request, capsys) -> None:
    """Test that unify raises if request chain within same set is not the same."""
    report1 = DiffReport("1", "1", request_chain=[], produced_request=BASIC_REQUEST)
    report2 = DiffReport(
        "1", "1", request_chain=[basic_request], produced_request=BASIC_REQUEST
    )
    with pytest.raises(ValueError, match="conflicting request chains"):
        DiffReport.unify({frozenset({report1, report2})})


def test_to_log(basic_request: Request) -> None:
    """Test writing a log file."""
    report = DiffReport(
        "lib1",
        "err1",
        request_chain=[basic_request],
        produced_request=basic_request,
        unique=True,
        detail="Test detail",
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        report.to_log(Path(temp_dir))

        with open(Path(temp_dir) / "err1_lib1.txt") as f:
            content = f.read()

    assert "lib1" in content
    assert "err1" in content
    assert "Error was unique" in content
    assert basic_request.method.value in content
    assert basic_request.path in content
    assert "Test detail" in content
