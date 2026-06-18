def test_runtime_legacy_imports_still_work():
    from webscoper.runtime.approvals import ApprovalStore
    from webscoper.runtime.evidence import EvidenceStore
    from webscoper.runtime.llm_config import LLMClientConfig
    from webscoper.runtime.llm_router import LLMProviderRouter
    from webscoper.runtime.pending import PendingApprovalManager
    from webscoper.runtime.report import FinalReportBuilder
    from webscoper.runtime.reviewer import ReportReviewer
    from webscoper.runtime.revise_loop import ReviewReviseLoop
    from webscoper.runtime.revision import ReviewRevisionPlanner
    from webscoper.runtime.risk_gate import RiskGate
    from webscoper.runtime.tool_call_parser import ToolCallParser
    from webscoper.runtime.tool_executor import LocalToolExecutor
    from webscoper.runtime.trace import TraceRecorder
    from webscoper.runtime.transcript import TranscriptStore

    assert EvidenceStore is not None
    assert FinalReportBuilder is not None
    assert TraceRecorder is not None
    assert TranscriptStore is not None
    assert ReportReviewer is not None
    assert ReviewRevisionPlanner is not None
    assert ReviewReviseLoop is not None
    assert RiskGate is not None
    assert ApprovalStore is not None
    assert PendingApprovalManager is not None
    assert LLMClientConfig is not None
    assert LLMProviderRouter is not None
    assert LocalToolExecutor is not None
    assert ToolCallParser is not None
