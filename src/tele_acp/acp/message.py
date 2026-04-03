from typing import Literal, TypeAlias, cast

import acp
from acp.schema import AudioContentBlock, EmbeddedResourceContentBlock, ImageContentBlock, ResourceContentBlock, StopReason, TextContentBlock
from pydantic import BaseModel

AcpAgentMessageChunk: TypeAlias = (
    acp.schema.AgentMessageChunk | acp.schema.AgentThoughtChunk | acp.schema.ToolCallStart | acp.schema.ToolCallProgress | acp.schema.AgentPlanUpdate
)
AcpContentBlock: TypeAlias = TextContentBlock | ImageContentBlock | AudioContentBlock | ResourceContentBlock | EmbeddedResourceContentBlock

_PartitionKey: TypeAlias = Literal["THINK", "MESSAGE", "TOOL"]
_PartitionPart: TypeAlias = list[acp.schema.AgentThoughtChunk] | list[acp.schema.AgentMessageChunk] | acp.schema.ToolCallProgress
_PartitionChunkType: TypeAlias = type[acp.schema.AgentThoughtChunk] | type[acp.schema.AgentMessageChunk] | type[acp.schema.ToolCallProgress]

# | acp.schema.AvailableCommandsUpdate
# | acp.schema.CurrentModeUpdate
# | acp.schema.ConfigOptionUpdate


class AcpMessage(BaseModel):
    # TODO: make it list and as message can handle queued messages.
    prompt: list[AcpContentBlock] = []

    # sessonInfo: acp.schema.SessionInfoUpdate
    model: acp.schema.CurrentModeUpdate | None = None

    delta: AcpAgentMessageChunk | None = None
    chunks: list[AcpAgentMessageChunk] = []

    usage: acp.schema.UsageUpdate | None = None
    stop_reason: StopReason | None = None

    def markdown(self) -> str:

        PARTITION_KEY: dict[_PartitionChunkType, _PartitionKey] = {
            acp.schema.AgentThoughtChunk: "THINK",
            acp.schema.AgentMessageChunk: "MESSAGE",
            acp.schema.ToolCallProgress: "TOOL",
        }

        parts_list: list[tuple[_PartitionKey, _PartitionPart]] = []

        for chunk in self.chunks:
            chunk_type = type(chunk)
            partition_key = PARTITION_KEY.get(cast(_PartitionChunkType, chunk_type))
            if partition_key is None:
                continue

            if partition_key == "TOOL":
                parts_list.append((partition_key, cast(acp.schema.ToolCallProgress, chunk)))
                continue

            tmp_key: _PartitionKey | None = None
            temp_part: _PartitionPart = []

            if len(parts_list) > 0:
                tmp_key, temp_part = parts_list.pop()

            if temp_part is None or tmp_key != partition_key:
                temp_part = []
                tmp_key = partition_key

            if tmp_key == partition_key:
                if partition_key == "THINK":
                    think_part = cast(list[acp.schema.AgentThoughtChunk], temp_part)
                    think_part.append(cast(acp.schema.AgentThoughtChunk, chunk))
                    parts_list.append((partition_key, think_part))
                else:
                    message_part = cast(list[acp.schema.AgentMessageChunk], temp_part)
                    message_part.append(cast(acp.schema.AgentMessageChunk, chunk))
                    parts_list.append((partition_key, message_part))
            else:
                if partition_key == "THINK":
                    parts_list.append((partition_key, [cast(acp.schema.AgentThoughtChunk, chunk)]))
                else:
                    parts_list.append((partition_key, [cast(acp.schema.AgentMessageChunk, chunk)]))

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

            tool_call_id = chunk.tool_call_id
            found = next((x for x in self.chunks if isinstance(x, acp.schema.ToolCallStart) and x.tool_call_id == tool_call_id), None)

            if found is None:
                return ""

            return f"> [{chunk.status}] {found.title}\n"

        for partition_key, temp_part in parts_list:
            if partition_key == "THINK":
                think_part = cast(list[acp.schema.AgentThoughtChunk], temp_part)
                description += "\n"
                description += "".join([_description_think(chunk) for chunk in think_part])
            elif partition_key == "MESSAGE":
                message_part = cast(list[acp.schema.AgentMessageChunk], temp_part)
                description += "\n"
                description += "".join([_description_message(chunk) for chunk in message_part])
                description += "\n"
            elif partition_key == "TOOL":
                content = _description_tool(cast(acp.schema.ToolCallProgress, temp_part))
                if content != "":
                    description += "\n"
                    description += content

        return description
