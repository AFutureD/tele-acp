from pathlib import Path


def get_agents_dir() -> Path:
    return Path(__file__).parent


def agent_system_instruction_file() -> Path:
    return get_agents_dir() / "system.md"
