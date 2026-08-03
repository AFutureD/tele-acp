

# susie

> El proyecto lleva el nombre de *Susie* de *Lord of the Mysteries*.  
> Es el golden retriever de Audrey, así como su amiga y asistente de confianza.  
> Consulte https://lordofthemysteries.fandom.com/wiki/Susie para más detalles.

**Chatea con agentes en Telegram a través de ACP y Codex app-server.**

Este proyecto permite que los agentes gestionen solicitudes de Telegram en mi nombre a través de canales de cuentas de usuario de Telegram o canales de la API de Bots.

> [!CAUTION]
> Este proyecto está en desarrollo activo.

## Inicio rápido

### 1. Instalación

```bash
uv tool install git+https://github.com/AFutureD/susie
```

### 2. Incorporar un canal de Telegram

Para permitir que Susie reciba mensajes de Telegram, incorpore al menos un canal primero.
Esto también actualizará la configuración del canal en el archivo de configuración.

```bash
susie onboard telegram_user
susie onboard telegram_user --qrcode  # imprimir un código QR ASCII en la terminal
susie auth me
```

Para un bot de Telegram:

```bash
susie onboard telegram_bot '<bot-token>'
susie onboard telegram_bot '<bot-token>' --id my_bot  # id de canal explícito opcional
```

### 3. Iniciar el servicio

```bash
susie start
```

### 4. Configuración

Después de iniciar el servicio, puede ajustar la configuración para adaptarla a sus necesidades.

Hay dos partes.

**Primera parte: Entorno de ejecución del agente**

> [!IMPORTANT]
> `agent_id = "codex"` utiliza Codex app-server a través del SDK oficial de Python `openai-codex`. Otros valores de `agent_id` se resuelven a través del registro de ACP.

Debe gestionar su entorno de ejecución del agente directamente en lugar de a través de Susie.

El directorio de trabajo es `~/.config/susie/workspace/<YOUR_ASSISTANT_ID>`.

> [!NOTE]
> Puede cambiar el directorio de trabajo en la configuración de Susie.

Al desarrollar desde un checkout de git, inicialice el SDK de Codex incluido:

```bash
git submodule update --init --recursive
uv sync
```


**Segunda parte: Susie**


El archivo de configuración de Susie se encuentra en `~/.config/susie/config.toml`.

Después de iniciar sesión en Telegram, este archivo ya debería haberse creado para usted.

Consulte [Configuración](./docs/Configutation.md) para obtener más detalles.

## Diseño

1. `Chat`: una unidad de conversación, como un chat uno a uno o un grupo de Telegram.
2. `Channel`: la capa de transporte que envía y recibe mensajes.
3. `Replier`: el componente que gestiona los mensajes entrantes y genera respuestas.
4. `Agent`: un entorno de ejecución de LLM respaldado por Codex app-server o ACP utilizado por un respondedor de asistente.
5. `Command Chain`: el despachador de comandos para los comandos con barra (/).

Un chat puede tener múltiples respondedores. Un respondedor de asistente está respaldado por un entorno de ejecución de agente.

La cadena de comandos se puede utilizar para controlar el chat, los respondedores o el estado global.
