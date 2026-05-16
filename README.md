# susie

> The project is named after *Susie* from *Lord of the Mysteries*.  
> She is Audrey’s golden retriever, as well as her friend and trusted assistant.  
> See https://lordofthemysteries.fandom.com/wiki/Susie for more details.

**Chat with agents on Telegram through ACP and Codex app-server.**

This project lets agents handle Telegram requests on my behalf through Telegram user-account channels or Bot API channels.

> [!CAUTION]
> This project is under active development.

## Quick Start

### 1. Install

```bash
uv tool install git+https://github.com/AFutureD/susie
```

### 2. Onboard a Telegram channel

To let Susie receive messages from Telegram, onboard at least one channel first.
This will also update the channel settings in the configuration file.

```bash
susie onboard telegram_user
susie onboard telegram_user --qrcode  # print an ASCII QR code in the terminal
susie auth me
```

For a Telegram bot:

```bash
susie onboard telegram_bot my_bot --token '<bot-token>'
```

### 3. Start the service

```bash
susie start
```

### 4. Configuration

After starting the service, you can adjust the configuration to match your needs.

There are two parts.

**Part one: Agent runtime**

> [!IMPORTANT]
> `agent_id = "codex"` uses Codex app-server through the official `openai-codex` Python SDK. Other `agent_id` values are resolved through the ACP registry.

You should manage your agent runtime directly rather than through Susie.

The working directory is `~/.config/susie/workspace/<YOUR_ASSISTANT_ID>`.

> [!NOTE]
> You can change the working directory in Susie's configuration.

When developing from a git checkout, initialize the vendored Codex SDK:

```bash
git submodule update --init --recursive
uv sync
```


**Part two: Susie**


Susie's configuration file is located at `~/.config/susie/config.toml`.

After you log in to Telegram, this file should already be created for you.

See [Configuration](./docs/Configutation.md) for details.

## Design

1. `Chat`: a conversation unit, such as a 1-to-1 chat or a Telegram group.
2. `Channel`: the transport layer that sends and receives messages.
3. `Replier`: the component that handles incoming messages and produces replies.
4. `Agent`: a Codex app-server or ACP-backed LLM runtime used by an assistant replier.
5. `Command Chain`: the command dispatcher for slash commands.

A chat may have multiple repliers. An assistant replier is backed by an agent runtime.

The command chain can be used to control the chat, the repliers, or global state.
