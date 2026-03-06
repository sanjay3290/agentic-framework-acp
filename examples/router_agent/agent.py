"""Router agent example: routes to different specialists based on input."""
from acp_agent_framework import Agent, Route, RouterAgent, serve

code_agent = Agent(
    name="code-expert",
    backend="claude",
    instruction="You are a coding expert. Help with code questions, debugging, and best practices.",
)

writing_agent = Agent(
    name="writing-expert",
    backend="claude",
    instruction="You are a writing expert. Help with essays, emails, and content creation.",
)

math_agent = Agent(
    name="math-expert",
    backend="claude",
    instruction="You are a math expert. Help with calculations, equations, and mathematical concepts.",
)

router = RouterAgent(
    name="smart-router",
    description="Routes questions to the right specialist",
    routes=[
        Route(keywords=["code", "python", "javascript", "bug", "function", "api"], agent=code_agent),
        Route(keywords=["write", "essay", "email", "blog", "content", "grammar"], agent=writing_agent),
        Route(keywords=["math", "calculate", "equation", "number", "algebra"], agent=math_agent),
    ],
    default_agent=code_agent,
)

if __name__ == "__main__":
    serve(router)
