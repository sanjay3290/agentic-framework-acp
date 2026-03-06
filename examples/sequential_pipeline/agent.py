"""Sequential pipeline example: research -> summarize -> format."""
from acp_agent_framework import Agent, SequentialAgent, serve

researcher = Agent(
    name="researcher",
    backend="claude",
    instruction="Research the given topic thoroughly. Provide detailed findings.",
    output_key="research",
)

summarizer = Agent(
    name="summarizer",
    backend="claude",
    instruction=lambda ctx: (
        f"Summarize this research concisely:\n\n{ctx.state.get('research', '')}"
    ),
    output_key="summary",
)

formatter = Agent(
    name="formatter",
    backend="claude",
    instruction=lambda ctx: (
        f"Format this summary as a professional report with headers:\n\n"
        f"{ctx.state.get('summary', '')}"
    ),
)

pipeline = SequentialAgent(
    name="research-pipeline",
    description="Research, summarize, and format a topic",
    agents=[researcher, summarizer, formatter],
)

if __name__ == "__main__":
    serve(pipeline)
