from typing import Annotated, NotRequired

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """Graph state. Keep it small: conversation + loop guard.

    Add fields here only for data the *graph* must route on. Business data belongs in
    tools and their storage, not in the state.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    steps: NotRequired[int]
