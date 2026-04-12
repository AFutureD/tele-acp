# Add QR Login Option

* Task: 260412T2244-add-auth-login-qrcode
* Author: [Huanan](https://github.com/AFutureD)
* Status: DONE
* Type: FEAT
* Related: []


## Background

`susie auth login` currently supports bot-token login and the standard phone/code flow for user accounts.

Telegram and Telethon also support QR-based login for user accounts, which is useful when the operator already has an authenticated Telegram app on another device.


## Goal

Add a CLI option to `susie auth login` that uses Telegram's QR-login flow for user accounts.


## Requirements

- Add a `--qrcode` flag to `susie auth login`.
- Keep `--bot` and `--qrcode` mutually exclusive.
- Reuse the existing local-session creation and channel-config update behavior after a successful login.
- Support accounts protected by Telegram Two-Step Verification by prompting for the password when required.
- Document the new login mode in the main user docs.


## Notes

- Telethon provides the QR login token and completion flow, but it does not render the QR image for us.
- The CLI now depends on `python-qrcode` to print an ASCII QR code directly in the terminal, while still showing the raw `tg://login?...` payload as a fallback.
