# susie

> The project is named after *Susie* from *Lord of the Mysteries*.  
> She is Audrey’s golden retriever, as well as her friend and trusted assistant.  
> See https://lordofthemysteries.fandom.com/wiki/Susie for more details.

**Chat with agents on Telegram through ACP.**

This project lets agents handle Telegram requests on my behalf through my personal account rather than through a bot.

> [!CAUTION]
> This project is under active development.

## Quick Start

### 1. Install

```bash
uv tool install git+https://github.com/AFutureD/susie
```

### 2. Log in to Telegram

To let Susie receive messages from Telegram, you need to log in first.
This will also update the channel settings in the configuration file.

```bash
susie auth login
susie auth me
```

### 3. Start the service

```bash
susie start
```

### 4. Configuration

After starting the service, you can adjust the configuration to match your needs.

There are two parts.

**Part one: ACP**

> [!IMPORTANT]
> At present, we only support Codex and Kimi.

You should manage your agent directly rather than through Susie.

The working directory is `~/.config/susie/workspace/<YOUR_AGENT_ID>`.

> [!NOTE]
> You can change the working directory in Susie's configuration.


**Part two: Susie**


Susie's configuration file is located at `~/.config/susie/config.toml`.

After you log in to Telegram, this file should already be created for you.

See [Configuration](./docs/Configutation.md) for details.

## Design

1. `Chat`: a conversation unit, such as a 1-to-1 chat or a Telegram group.
2. `Channel`: the transport layer that sends and receives messages.
3. `Replier`: the component that handles incoming messages and produces replies.
4. `Agent`: an ACP-backed LLM agent used by an agent replier.
5. `Command Chain`: the command dispatcher for slash commands.

A chat may have multiple repliers. An agent replier is backed by an agent.

The command chain can be used to control the chat, the repliers, or global state.
