"""Unit tests for DiffReport."""

import pytest

from telephuzz.evaluation.report import DiffReport
from telephuzz.http_message import Request


def test_init(basic_request: Request) -> None:
    """Test basic init."""
    lib_id = "TestLib1"
    err_id = "Error1"

    report = DiffReport(
        library_id=lib_id,
        error_id=err_id,
        persistent=False,
        request_chain=[basic_request],
    )

    assert report.library_id == lib_id
    assert report.error_id == err_id
    assert not report.persistent
    assert len(report.request_chain) == 1 and report.request_chain[0] == basic_request
    assert report.unique, "Default unique value should be True"
    assert report.detail == "", "Default detail should be empty"


def test_compare(basic_request: Request) -> None:
    """Test __hash__ and __eq__ methods."""
    eq_report_1 = DiffReport("Eq1", "Err1", False, [basic_request])
    # different request chain is not considered
    eq_report_2 = DiffReport("Eq1", "Err1", False, [])
    # persistance should cause it to be unequeal
    uneq_report = DiffReport("Eq1", "Err1", True, [basic_request])

    assert eq_report_1 == eq_report_2
    assert eq_report_1 != uneq_report

    assert len({eq_report_1, eq_report_2, uneq_report}) == 2


def test_unify_persistent() -> None:
    """Assert that persistent is True as long as one report claims persistancy."""
    reports = {
        frozenset(
            {
                DiffReport("1", "2", persistent=False, request_chain=[]),
                DiffReport("1", "2", persistent=True, request_chain=[]),
                DiffReport("1", "2", persistent=False, request_chain=[]),
            }
        )
    }

    unified_reports = DiffReport.unify(reports)
    assert len(unified_reports) == 1

    assert unified_reports.pop() == DiffReport(
        "1", "2", persistent=True, request_chain=[]
    )


def test_unify_detail() -> None:
    """Assert that details are concatenated."""
    reports = {
        frozenset(
            {
                DiffReport(
                    "1",
                    "2",
                    persistent=False,
                    request_chain=[],
                    detail="Detail1",
                ),
                DiffReport(
                    "1",
                    "2",
                    persistent=False,
                    request_chain=[],
                    detail="Detail2",
                ),
            }
        )
    }

    unified_reports = DiffReport.unify(reports)
    assert len(unified_reports) == 1

    unified_detail = unified_reports.pop().detail
    assert "Detail1" in unified_detail and "Detail2" in unified_detail


def test_unique_assignment() -> None:
    """Test correct uniqueness assignment."""
    unique_report = DiffReport("1", "1", False, [])
    same_error_report1 = DiffReport("1", "2", False, [])
    same_error_report2 = DiffReport("2", "2", False, [])
    same_error_report3 = DiffReport("3", "2", False, [])
    same_error_report4 = DiffReport("4", "2", False, [])

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
        (DiffReport("1", "1", False, []), DiffReport("2", "1", False, [])),
        (DiffReport("1", "1", False, []), DiffReport("1", "2", False, [])),
    ],
    ids=["library_id", "error_id"],
)
def test_id_mismatch(report1: DiffReport, report2: DiffReport) -> None:
    """Test that unify raises if two ids within same set are not the same."""
    with pytest.raises(ValueError, match="different libraries or errors"):
        DiffReport.unify({frozenset({report1, report2})})


def test_request_chain_mismatch(basic_request: Request, capsys) -> None:
    """Test that unify raises if request chain within same set is not the same."""
    report1 = DiffReport("1", "1", False, [])
    report2 = DiffReport("1", "1", True, [basic_request])  # TODO hash for Request
    with pytest.raises(ValueError, match="conflicting request chains"):
        DiffReport.unify({frozenset({report1, report2})})
