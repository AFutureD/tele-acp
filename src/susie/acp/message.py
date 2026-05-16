from typing import Literal, TypeAlias

import acp
from acp.schema import AudioContentBlock, EmbeddedResourceContentBlock, ImageContentBlock, ResourceContentBlock, StopReason, TextContentBlock
from pydantic import BaseModel
from susie_core import ChatMessagePart, ChatMessageTextPart
from susie_core.chat import ChatMessageBlockQuote

AcpAgentMessageChunk: TypeAlias = (
    acp.schema.AgentMessageChunk | acp.schema.AgentThoughtChunk | acp.schema.ToolCallStart | acp.schema.ToolCallProgress | acp.schema.AgentPlanUpdate
)
AcpContentBlock: TypeAlias = TextContentBlock | ImageContentBlock | AudioContentBlock | ResourceContentBlock | EmbeddedResourceContentBlock

_SectionKey: TypeAlias = Literal["THINK", "MESSAGE", "TOOL"]

# | acp.schema.AvailableCommandsUpdate
# | acp.schema.CurrentModeUpdate
# | acp.schema.ConfigOptionUpdate


def _description_content_chunk(chunk: acp.schema.ContentChunk) -> str:
    content = chunk.content
    if isinstance(content, TextContentBlock):
        return content.text
    if isinstance(content, ImageContentBlock):
        return "ImageContentBlock"
    if isinstance(content, AudioContentBlock):
        return "AudioContentBlock"
    if isinstance(content, ResourceContentBlock):
        return "ResourceContentBlock"
    if isinstance(content, EmbeddedResourceContentBlock):
        return "EmbeddedResourceContentBlock"
    return ""


class AcpMessage(BaseModel):
    # TODO: make it list and as message can handle queued messages.
    prompt: list[AcpContentBlock] = []

    # sessonInfo: acp.schema.SessionInfoUpdate
    model: acp.schema.CurrentModeUpdate | None = None

    delta: AcpAgentMessageChunk | None = None
    chunks: list[AcpAgentMessageChunk] = []

    usage: acp.schema.UsageUpdate | None = None
    stop_reason: StopReason | None = None

    def chat_message_parts(self) -> list[ChatMessagePart]:

        ret: list[ChatMessagePart] = []

        for chunk in self.chunks:
            match chunk:
                case acp.schema.AgentMessageChunk():
                    ret.append(ChatMessageTextPart(_description_content_chunk(chunk)))

                case acp.schema.AgentThoughtChunk():
                    ret.append(ChatMessageTextPart(_description_content_chunk(chunk)))

                case acp.schema.ToolCallStart():
                    status = chunk.status
                    title = chunk.title
                    content = str(chunk.raw_input)
                    ret.append(ChatMessageBlockQuote(f"[{status}] {title}", content))

                case acp.schema.ToolCallProgress():
                    the_tool_start_chunk = next(
                        (c for c in self.chunks if isinstance(c, acp.schema.ToolCallStart) and c.tool_call_id == chunk.tool_call_id), None
                    )

                    status = chunk.status
                    title = chunk.title
                    content = str(chunk.content)

                    if (chunk.title is None or chunk.title == "") and the_tool_start_chunk is not None:
                        title = the_tool_start_chunk.title

                    ret.append(ChatMessageBlockQuote(f"[{status}] {title}", content))

                case acp.schema.AgentPlanUpdate():
                    pass

        return ret
