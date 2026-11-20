"""Regression Drift Classifier establishing deterministic classification between base and PR."""

from __future__ import annotations

import logging
from tracecase.ci.baseline.models import BaselineTestOutcome
from tracecase.ci.drift.models import DriftClassification

logger = logging.getLogger("tracecase.ci.drift.classifier")


class RegressionDriftClassifier:
    """Classifies test outcome changes between base branch baseline and PR execution."""

    @staticmethod
    def classify(
        pr_status: str,
        base_outcome: BaselineTestOutcome | None = None,
        pr_test_revision_hash: str = "",
    ) -> tuple[DriftClassification, str, bool]:
        """Classify test change into a deterministic DriftClassification.
        
        Returns:
            (classification, explanation, test_definition_drift)
        """
        # 1. PR Infrastructure / execution crash
        if pr_status == "error":
            return (
                DriftClassification.INFRASTRUCTURE_ERROR,
                "Internal runner or browser crash occurred during PR execution.",
                False,
            )

        # 2. PR Skipped or cancelled
        if pr_status in ("skipped", "cancelled"):
            return (
                DriftClassification.SKIPPED,
                f"Test execution was {pr_status} on PR run.",
                False,
            )

        # 3. Missing Baseline Handling (Never interpret missing as passing!)
        if base_outcome is None:
            if pr_status == "failed":
                return (
                    DriftClassification.UNKNOWN_BASELINE_FAILURE,
                    "Test failed on PR run with no baseline record available. Cannot determine whether failure was introduced by this change or pre-existing.",
                    False,
                )
            if pr_status == "flaky":
                return (
                    DriftClassification.UNKNOWN_BASELINE_FAILURE,
                    "Test was flaky on PR run with no baseline record available.",
                    False,
                )
            return (
                DriftClassification.NEW_TEST_PASS,
                "New test or test without previous baseline passed successfully.",
                False,
            )

        # 4. Check test definition drift
        base_rev = base_outcome.test_revision_hash
        test_def_drift = bool(
            base_rev and pr_test_revision_hash and base_rev != pr_test_revision_hash
        )
        drift_note = " (Note: Test definition changed between base and PR.)" if test_def_drift else ""

        base_st = base_outcome.status

        # 5. Core transition taxonomy
        if base_st in ("cancelled", "crashed", "aborted"):
            if pr_status == "failed":
                return (
                    DriftClassification.UNKNOWN_BASELINE_FAILURE,
                    f"Base execution was {base_st}; baseline outcome is invalid and cannot be compared.{drift_note}",
                    test_def_drift,
                )
            if pr_status == "passed":
                return (
                    DriftClassification.NEW_TEST_PASS,
                    f"Test passed on PR (base execution was {base_st}).{drift_note}",
                    test_def_drift,
                )

        if base_st == "passed":
            if pr_status == "failed":
                return (
                    DriftClassification.NEW_REGRESSION,
                    f"New regression introduced by PR: Test passed on base commit but failed on PR.{drift_note}",
                    test_def_drift,
                )
            if pr_status == "flaky":
                return (
                    DriftClassification.NEWLY_FLAKY,
                    f"Newly unstable test: Test was stable on base commit but required retry recovery on PR.{drift_note}",
                    test_def_drift,
                )
            # Passed -> Passed
            if test_def_drift:
                return (
                    DriftClassification.STABLE_PASS,
                    f"Passed with test definition drift: Test passed on both base and PR, but definition (locators or steps) changed.{drift_note}",
                    True,
                )
            return (
                DriftClassification.STABLE_PASS,
                "Stable test: Passed on both base commit and PR.",
                False,
            )

        if base_st == "failed":
            if pr_status == "failed":
                return (
                    DriftClassification.PRE_EXISTING_FAILURE,
                    f"Pre-existing failure: Test was already failing on base commit before this PR was created.{drift_note}",
                    test_def_drift,
                )
            if pr_status == "flaky":
                return (
                    DriftClassification.PARTIAL_RECOVERY,
                    f"Partially recovered: Test was failing on base commit and passed on retry on PR.{drift_note}",
                    test_def_drift,
                )
            if pr_status == "passed":
                return (
                    DriftClassification.FIXED_REGRESSION,
                    f"Fixed regression: Test was failing on base commit and has been fixed by this PR!{drift_note}",
                    test_def_drift,
                )

        if base_st == "flaky":
            if pr_status == "flaky":
                return (
                    DriftClassification.PERSISTENT_FLAKY,
                    f"Persistent flakiness: Test exhibited flaky behavior on both base commit and PR.{drift_note}",
                    test_def_drift,
                )
            if pr_status == "failed":
                return (
                    DriftClassification.NEW_REGRESSION,
                    f"Regression: Previously flaky test has now degraded to complete failure on PR (worsened instability).{drift_note}",
                    test_def_drift,
                )
            return (
                DriftClassification.STABLE_PASS,
                f"Stabilized test: Test was flaky on base commit and passed cleanly on PR.{drift_note}",
                test_def_drift,
            )

        # Fallback for base infrastructure errors (baseline unknown)
        if base_st == "error":
            if pr_status == "passed":
                return (
                    DriftClassification.NEW_TEST_PASS,
                    f"Test passed on PR; base commit encountered infrastructure error so baseline test outcome is unknown.{drift_note}",
                    test_def_drift,
                )
            return (
                DriftClassification.UNKNOWN_BASELINE_FAILURE,
                f"Base commit run encountered infrastructure error; baseline outcome is unknown and cannot confirm regression.{drift_note}",
                test_def_drift,
            )

        return (
            DriftClassification.STABLE_PASS,
            f"Test completed on PR.{drift_note}",
            test_def_drift,
        )
