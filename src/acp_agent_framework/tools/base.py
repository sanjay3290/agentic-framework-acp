"""Base tool interface."""
import asyncio
from abc import ABC, abstractmethod
from typing import Any

class BaseTool(ABC):
    name: str
    description: str

    @abstractmethod
    def run(self, args: dict[str, Any]) -> Any:
        """Execute the tool synchronously."""
        ...

    async def arun(self, args: dict[str, Any]) -> Any:
        """Execute the tool asynchronously. Defaults to running sync `run()` in a thread."""
        return await asyncio.to_thread(self.run, args)

    @abstractmethod
    def get_schema(self) -> dict[str, Any]: ...
