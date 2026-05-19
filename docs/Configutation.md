# Configuration

## 1. Configuration Location

Susie's all settings are stored under `~/.config/susie/`.

- configuration: `~/.config/susie/config.toml`
- assistant workspace: `~/.config/susie/workspace/<assistant-id>/`

## 2. Default Configuration

```toml
# See https://core.telegram.org/api/obtaining_api_id for how to obtain your api_id and api_hash.
api_id = 17349
api_hash = "344583e45741c457fe1862106095a5eb"

# No channels are configured by default.
[channels]

# Example: a Telegram user-account channel.
[channels.my_account]
type = "telegram_user"

# The session name for the Telegram client. You should not change it.
session_name = "75d52b5e-3326-4ed1-ab16-fee65a4dbace"

# Whether users in your contacts are allowed access.
allow_contacts = true

# Optional: whitelist of allowed users (peer IDs).
whitelist = []

# Optional: per-group policy. "*" matches all groups.
[channels.my_account.groups."*"]

# Optional: whitelist of allowed users (peer IDs).
whitelist = ["*"]

# Weather only response to mentioned messages
only_mention = true

# Example: a Telegram Bot API channel.
[channels.my_bot]
type = "telegram_bot"
token = "123456:bot-token"
whitelist = ["*"]
drop_pending_updates = false

[channels.my_bot.groups."*"]
whitelist = ["*"]
only_mention = true

[[assistants]]
# The ID of the assistant.
id = "default"

# The agent runtime ID used by this assistant.
# "codex" uses Codex app-server through the official openai-codex SDK.
# Other values are resolved through the ACP registry.
agent_id = "codex"

# Example: bind all chats on `my_account` to the default assistant.
[[bindings]]
channel = "my_account"
assistant_id = "default"
chat_ids = ["*"]
```

## 3. FAQ

### 3.1 How do I configure an assistant working directory?

You can set an assistant's working directory with `work_dir` inside `[[assistants]]`.

Example:

```toml
[[assistants]]
id = "default"
agent_id = "codex"
work_dir = "/absolute/path/to/your/project"
```

If `work_dir` is not set, Susie will automatically use the default directory for that assistant:

```text
~/.config/susie/workspace/<assistant-id>/
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
groups."*" = { whitelist = ["*"], only_mention = true }
```

Notes:

- `susie onboard telegram_user` usually writes a user-channel configuration automatically.
- `susie onboard telegram_user --qrcode` uses Telegram's QR-login flow for user accounts and prints an ASCII QR code in the terminal.
- `session_name` is the name of the local Telegram session.
- `whitelist` limits which peer IDs or group IDs are allowed.
- `allow_contacts` controls whether Telegram contacts are allowed.

Example for a bot channel:

```toml
[channels.my_bot]
type = "telegram_bot"
token = "123456:bot-token"
whitelist = ["*"]
drop_pending_updates = false

[channels.my_bot.groups."*"]
whitelist = ["*"]
only_mention = true
```

You can write this with:

```bash
susie onboard telegram_bot '<bot-token>'
susie onboard telegram_bot '<bot-token>' --id my_bot
```

> [!NOTE]
> We recommend using the `susie` CLI to modify channel settings.


### 3.3 How do I configure bindings?

> [!CAUTION]
> This is not fully supported yet and is still under development.

`bindings` are used to connect a channel to an assistant.

The simplest example:

```toml
[[bindings]]
channel = "my_account"
assistant_id = "default"
```

If you define multiple assistants, you can assign them by channel:

```toml
[[assistants]]
id = "ops"
agent_id = "codex"
work_dir = "/absolute/path/to/ops-workspace"

[[bindings]]
channel = "my_account"
assistant_id = "ops"
```

You can also bind specific chats to a different assistant:

```toml
[[bindings]]
channel = "my_account"
chat_ids = ["123456789", "G987654321"]
assistant_id = "ops"

[[bindings]]
channel = "my_account"
assistant_id = "default"
```

Notes:

- `channel` must match the key used in `[channels.<id>]`, not `session_name`.
- `chat_ids` is optional. When present, the binding only matches those chats. A single `chat_id` value is also accepted and normalized to `chat_ids = ["..."]`.
- `assistant_id` must reference an assistant `id` already defined in `[[assistants]]`.
- Bindings first try to match `channel + chat_ids`, then fall back to the first binding that matches only `channel`.
- If no binding matches, Susie falls back to the `default` assistant for that channel.

### 3.4 How do I change the agent runtime used by an assistant?

Set `agent_id` in the corresponding `[[assistants]]` entry:

```toml
[[assistants]]
id = "default"
agent_id = "codex"
```

`agent_id = "codex"` uses Codex app-server through the official `openai-codex` SDK.
Other values are treated as ACP registry IDs, such as `codex-acp` or `kimi`.

> [!NOTE]
> The ACP registry remains available for non-`codex` agent runtimes.
