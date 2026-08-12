import httpx

from issuepilot.domain import DiagnoseRequest, KnowledgeDocument
from issuepilot.generator import OpenAIResponsesGenerator
from issuepilot.retrieval import HybridRetriever
from issuepilot.trace import InMemoryTraceStore
from issuepilot.workflow import DiagnosisWorkflow


def test_openai_generator_uses_structured_responses_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.openai.com/v1/responses"
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={"output": [{"content": [{"type": "output_text", "text": "Grounded draft"}]}]},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        generator = OpenAIResponsesGenerator(api_key="test-key", model="test-model", http=http)
        assert generator.generate("issue", "evidence") == "Grounded draft"


def test_workflow_labels_model_generated_result() -> None:
    class Generator:
        name = "test-model"

        def generate(self, query: str, evidence: str) -> str:
            assert "Install fails" in query
            assert "supported installer" in evidence
            return "Use the supported installer [doc-1]."

    document = KnowledgeDocument(
        id="doc-1",
        title="Install guide",
        text="Use the supported installer.",
        source_url="https://example.com/install",
        kind="documentation",
    )
    workflow = DiagnosisWorkflow(
        HybridRetriever([document]), InMemoryTraceStore(), generator=Generator()
    )

    result = workflow.diagnose(DiagnoseRequest(title="Install fails", body="installer error"))

    assert result.mode == "model"
    assert result.draft == "Use the supported installer [doc-1]."
