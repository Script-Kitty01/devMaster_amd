import unittest
from pathlib import Path
from unittest.mock import Mock

from src.agents.review_agent import ReviewAgent
from src.graph.task_workflow import TaskWorkflow
from src.models.artifacts import Evidence, PatchProposal, VerificationResult
from src.state.task_state import initial_task_state


class TaskWorkflowContractTests(unittest.TestCase):
    def test_change_tasks_require_approval(self):
        workflow = object.__new__(TaskWorkflow)
        workflow.auto_approve = False
        state = initial_task_state(repo_path=str(Path.cwd()), task_text="Fix the auth bug")

        intake = workflow._node_intake(state)
        self.assertEqual(intake["task_brief"]["intent"], "change")
        self.assertTrue(intake["approval_required"])
        self.assertEqual(workflow._route_after_approval({"approved": False}), "report")

    def test_review_rejects_patch_without_evidence(self):
        agent = ReviewAgent(llm=Mock())
        patch = PatchProposal(
            id="patch-1",
            summary="change",
            rationale="",
            files_changed=["app.py"],
            unified_diff="diff --git a/app.py b/app.py",
            linked_evidence_ids=[],
            risk_level="low",
            verification_commands=[["pytest", "-q"]],
        )
        result = agent.review(
            task_text="fix",
            patch_proposal=patch,
            verification_results=[VerificationResult(
                check_id="check-1", name="pytest", command=["pytest"],
                status="passed", exit_code=0, summary="passed", output_path="",
            )],
            evidence=[],
            diagnoses=[],
        )
        self.assertEqual(result["verdict"], "request_revision")

    def test_review_rejects_failed_verification(self):
        agent = ReviewAgent(llm=Mock())
        evidence = Evidence(id="ev-1", source="read_file", file_path="app.py", excerpt="bug")
        patch = PatchProposal(
            id="patch-1", summary="change", rationale="", files_changed=["app.py"],
            unified_diff="diff --git a/app.py b/app.py", linked_evidence_ids=["ev-1"],
            risk_level="medium", verification_commands=[["pytest", "-q"]],
        )
        result = agent.review(
            task_text="fix",
            patch_proposal=patch,
            verification_results=[VerificationResult(
                check_id="check-1", name="pytest", command=["pytest"],
                status="failed", exit_code=1, summary="failed", output_path="",
            )],
            evidence=[evidence],
            diagnoses=[],
        )
        self.assertEqual(result["verdict"], "reject")


if __name__ == "__main__":
    unittest.main()
