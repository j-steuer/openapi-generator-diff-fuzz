"""File for storing the results of an evaluation if a difference is found."""

from dataclasses import dataclass
from pathlib import Path

from telephuzz.http_message import Request
from telephuzz.session.client_library import LibraryId


@dataclass
class DiffReport:
    """Class for storing and writing the results of an evaluation."""

    library_id: LibraryId
    error_id: str
    persistent: bool
    request_chain: list[Request]
    request_only: bool = True
    unique: bool = True
    detail: str = ""

    @classmethod
    def unify(cls, reports: set[frozenset["DiffReport"]]) -> set["DiffReport"]:
        """Merge and normalize groups of reports describing the same error.

        This method consolidates multiple DiffReport instances that refer to the
        same library and error. It also checks the uniqueness of errors within
        the set of all reports.

        Args:
            reports: A set of report groups. Each inner set contains DiffReport
                instances that refer to the same library and error.

        Returns:
            A set of unified DiffReport instances, with one report per unique
            library–error combination. The unique attribute is to False
            if the error also occurs in other libraries.

        """
        unified_reports: dict[str, list["DiffReport"]] = dict()

        def _add_to_unified_reports(report: DiffReport):
            """Add report to dict based on error id, adjust unique if needed."""
            error_id = report.error_id
            if error_id not in unified_reports:
                # add entry for new error id
                unified_reports[error_id] = [report]

            else:
                if len(unified_reports[error_id]) == 1:
                    # correct the unique value of the first report
                    unified_reports[error_id][0].unique = False
                # set the unique value of all subsequent reports to false
                report.unique = False
                unified_reports[error_id].append(report)

        # sort for deterministic detail merge
        for report_set in reports:
            sample_report = next(iter(report_set))

            if len(report_set) == 1:
                # no need to unify anything
                _add_to_unified_reports(sample_report)
                continue

            library_id = sample_report.library_id
            error_id = sample_report.error_id
            persistent = False
            request_only = True
            request_chain = sample_report.request_chain
            details: list[str] = []

            for report in report_set:
                # library and error should match within set
                if report.library_id != library_id or report.error_id != error_id:
                    raise ValueError(
                        f"Reports within report set refer to "
                        f"different libraries or errors: {report_set}"
                    )

                # request chain should match within set
                if report.request_chain != request_chain:
                    raise ValueError(
                        f"Reports within report set have "
                        f"conflicting request chains: {report_set}"
                    )

                # request only as long as no report contradicts
                request_only = (
                    report.request_only if not report.request_only else request_only
                )

                # unified report is persistent as long as one report claims persistency
                persistent = report.persistent if report.persistent else persistent

                # collect all details
                if report.detail:
                    details.append(report.detail)

            _add_to_unified_reports(
                DiffReport(
                    library_id=library_id,
                    error_id=error_id,
                    persistent=persistent,
                    request_chain=request_chain,
                    detail=" | ".join(sorted(details)),  # deterministic detail merging
                )
            )

        return {
            report for error_sets in unified_reports.values() for report in error_sets
        }

    def __eq__(self, other):
        """Eq method."""
        # TODO add request chain once Request has hash
        if not isinstance(other, DiffReport):
            return False
        return (
            self.library_id,
            self.error_id,
            self.unique,
            self.persistent,
            self.detail,
        ) == (
            other.library_id,
            other.error_id,
            other.unique,
            other.persistent,
            other.detail,
        )

    def __hash__(self):
        """Hash method."""
        return hash(
            (
                self.library_id,
                self.error_id,
                self.unique,
                self.persistent,
                self.detail,
            )
        )

    def to_log(self, log_path: Path) -> None:
        """Write the information contained in the report to a log file."""
        error_str = f"Error report {self.error_id}\n"
        error_str += "----------------------------\n"

        error_str += "Requests:\n"
        for request in self.request_chain:
            error_str += repr(request) + "\n"
        error_str += "----------------------------\n"

        error_str += f"Error occured in library {self.library_id}:\n"

        request_only = "Only the request showed deviations.\n"
        if self.request_only:
            error_str += request_only

        unique = "Error was unique and only occured in this client.\n"
        not_unique = "Error was not unique and occured in other clients.\n"
        error_str += unique if self.unique else not_unique

        persistent = (
            "A change was detected in the database, implying a persistent error.\n"
        )
        not_persistent = "No deviation in the database state was detected.\n"
        error_str += persistent if self.persistent else not_persistent

        error_str += self.detail

        # TODO format, JSON?
        file_name = f"{self.error_id}_{self.library_id}.txt"
        with open(log_path / file_name, "w") as f:
            f.write(error_str)
