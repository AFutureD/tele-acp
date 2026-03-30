# Configuration

## 1. Configuration Location

Susie's all settings are stored under `~/.config/susie/`.

- configuration: `~/.config/susie/config.toml`
- agent workspace: `~/.config/susie/workspace/<agent_id>/`

## 2. Default Configuration

```toml
# See https://core.telegram.org/api/obtaining_api_id for how to obtain your api_id and api_hash.
api_id = 17349
api_hash = "344583e45741c457fe1862106095a5eb"

[channels]

# Example: a channel with the id `you_telegram_account_name`
[channels.you_telegram_account_name]
type = "telegram_user"

# The session name for the Telegram client. You should not change it.
session_name = "75d52b5e-3326-4ed1-ab16-fee65a4dbace"

# The whitelist of chat IDs that are allowed access.
whitelist = []

# Whether users in your contacts are allowed access.
allow_contacts = true

[[agents]]
# The ID of the agent.
id = "default"

# The ACP client ID used by this agent.
acp_id = "codex"

# Example:
# Chat ID used for report messages from this agent.
forward_to = ""

# Example: the default binding. 
# [[bindings]]
# # The ID of the `Agent`
# agent = "default"
#
# # The ID of the `Channel`
# channel = "you_telegram_account_name"
#
# # Optional: only match these chat IDs.
# # chat_ids = ["123456789", "G987654321"]
```

## 3. FAQ

### 3.1 How do I configure an agent working directory?

You can set an agent's working directory with `work_dir` inside `[[agents]]`.

Example:

```toml
[[agents]]
id = "default"
acp_id = "codex"
work_dir = "/absolute/path/to/your/project"
```

If `work_dir` is not set, Susie will automatically use the default directory for that agent:

```text
~/.config/susie/workspace/<agent_id>/
```

### 3.2 How do I configure a channel?

`channels` is a table keyed by channel ID. This key is also the value referenced later by `bindings`.

Example for a user-account channel:

```toml
[channels.my_account]
type = "telegram_user"
session_name = "my_account"
allow_contacts = true
whitelist = []
```

Example for a bot channel:

```toml
[channels.my_bot]
type = "telegram_bot"
session_name = "my_bot"
token = "123456:example-token"
whitelist = []
```

Notes:

- `susie auth login` usually writes a user-channel configuration automatically.
- `session_name` is the name of the local Telegram session.
- `whitelist` limits which peer IDs or group IDs are allowed.
- `allow_contacts` only applies to `telegram_user`.
- `token` only applies to `telegram_bot`.

> [!NOTE]
> We recommend using the `susie` CLI to modify channel settings.


### 3.3 How do I configure bindings?

> [!CAUTION]
> This is not fully supported yet and is still under development.

`bindings` are used to connect a channel to an agent.

The simplest example:

```toml
[[bindings]]
channel = "my_account"
agent = "default"
```

If you define multiple agents, you can assign them by channel:

```toml
[[agents]]
id = "ops"
acp_id = "codex"
work_dir = "/absolute/path/to/ops-workspace"

[[bindings]]
channel = "my_account"
agent = "ops"
```

You can also bind specific chats to a different agent:

```toml
[[bindings]]
channel = "my_account"
chat_ids = ["123456789", "G987654321"]
agent = "ops"

[[bindings]]
channel = "my_account"
agent = "default"
```

Notes:

- `channel` must match the key used in `[channels.<id>]`, not `session_name`.
- `chat_ids` is optional. When present, the binding only matches those chats. A single `chat_id` value is also accepted and normalized to `chat_ids = ["..."]`.
- `agent` must reference an agent ID already defined in `[[agents]]`.
- Bindings first try to match `channel + chat_ids`, then fall back to the first binding that matches only `channel`.
- If no binding matches, Susie falls back to the `default` agent for that channel.
