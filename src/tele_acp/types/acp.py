from typing import TypeAlias

import acp
from acp.schema import AudioContentBlock, EmbeddedResourceContentBlock, ImageContentBlock, ResourceContentBlock, TextContentBlock
from pydantic import BaseModel

AcpMessageChunk: TypeAlias = (
    acp.schema.AgentMessageChunk | acp.schema.AgentThoughtChunk | acp.schema.ToolCallStart | acp.schema.ToolCallProgress | acp.schema.AgentPlanUpdate
)

# | acp.schema.AvailableCommandsUpdate
# | acp.schema.CurrentModeUpdate
# | acp.schema.ConfigOptionUpdate


class AcpMessage(BaseModel):
    prompt: acp.schema.UserMessageChunk | str | None

    # sessonInfo: acp.schema.SessionInfoUpdate
    model: acp.schema.CurrentModeUpdate | None
    chunks: list[AcpMessageChunk] = []
    usage: acp.schema.UsageUpdate | None
    in_turn: bool = True

    def markdown(self) -> str:
        def content_text(content: object) -> str:
            if isinstance(content, acp.schema.TextContentBlock):
                return content.text
            return ""

        def quote(text: str) -> str:
            return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())

        def tool_label(chunk: acp.schema.ToolCallStart | acp.schema.ToolCallProgress) -> str:
            if chunk.title:
                return chunk.title
            if chunk.kind:
                return chunk.kind
            return chunk.tool_call_id

        PARTITION_KEY = {acp.schema.AgentThoughtChunk: "THNIK", acp.schema.AgentMessageChunk: "MESSAGE", acp.schema.ToolCallProgress: "TOOL"}

        parts_list: list[tuple[str, list[acp.schema.AgentThoughtChunk] | list[acp.schema.AgentMessageChunk] | acp.schema.ToolCallProgress]] = []

        for chunk in self.chunks:
            chunk_type = type(chunk)
            partition_key = PARTITION_KEY.get(chunk_type)
            if partition_key is None:
                continue

            if partition_key == "TOOL":
                parts_list.append((partition_key, chunk))  # type: ignore
                continue

            if len(parts_list) == 0:
                tmp_key, temp_part = (None, [])
            else:
                tmp_key, temp_part = parts_list.pop()

            if temp_part is None or tmp_key != partition_key:
                temp_part = []
                tmp_key = partition_key

            if tmp_key == partition_key:
                temp_part.append(chunk)  # type: ignore
                parts_list.append((partition_key, temp_part))  # type: ignore
            else:
                parts_list.append((partition_key, temp_part))  # type: ignore
                tmp_parts_list.append((partition_key, [chunk]))  # type: ignore

        description: str = ""

        def _description_think(chunk: acp.schema.AgentThoughtChunk) -> str:
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

        def _description_message(chunk: acp.schema.AgentMessageChunk) -> str:
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

        def _description_tool(chunk: acp.schema.ToolCallProgress) -> str:
            if not chunk.status or chunk.status not in ["completed", "failed"]:
                return ""
            return f"> [{chunk.status}] {chunk.kind} {chunk.title} "

        for partition_key, temp_part in parts_list:
            if partition_key == "THNIK":
                description += "".join([_description_think(chunk) for chunk in temp_part])  # type: ignore
            elif partition_key == "MESSAGE":
                description += "".join([_description_message(chunk) for chunk in temp_part])  # type: ignore
            elif partition_key == "TOOL":
                content = _description_tool(temp_part)  # type: ignore
                if content != "":
                    description += "\n"
                    description += content  # type: ignore
                    description += "\n"

        return description
