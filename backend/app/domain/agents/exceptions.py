"""Agent domain exceptions."""


class AgentBaseError(Exception):
    """Base exception for the agents domain."""

    def __init__(self, message: str = "Agent error"):
        self.message = message
        super().__init__(self.message)


class ConversationNotFoundError(AgentBaseError):
    """Raised when a conversation is not found."""

    def __init__(self, conversation_id: str):
        super().__init__(f"Conversation not found: {conversation_id}")
        self.conversation_id = conversation_id


class MessageNotFoundError(AgentBaseError):
    """Raised when a message is not found."""

    def __init__(self, message_id: str):
        super().__init__(f"Message not found: {message_id}")
        self.message_id = message_id


class AgentExecutionError(AgentBaseError):
    """Raised when agent execution fails."""

    def __init__(self, message: str = "Agent execution failed"):
        super().__init__(message)


class ToolExecutionError(AgentBaseError):
    """Raised when a tool call fails."""

    def __init__(self, tool_name: str, message: str = "Tool execution failed"):
        super().__init__(f"Tool '{tool_name}' failed: {message}")
        self.tool_name = tool_name


class ConversationAccessDenied(AgentBaseError):
    """Raised when user tries to access another user's conversation."""

    def __init__(self) -> None:
        super().__init__("Access denied to this conversation")
