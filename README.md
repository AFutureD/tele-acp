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
uv tool install git+https://github.com/AFutureD/tele-acp
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

You should manage your agent directly rather than through Susie.

The working directory is `~/.config/susie/workspace/<YOUR_AGENT_ID>`.

> [!NOTE]
> You can change the working directory in Susie's configuration.


**Part two: Susie**


Susie's configuration file is located at `~/.config/susie/config.toml`.

After you log in to Telegram, this file should already be created for you.

See [Configuration](./docs/Configutation.md) for details.
