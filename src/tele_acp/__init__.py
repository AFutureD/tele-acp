import logging

# sh = logging.StreamHandler()
# sh.setLevel(logging.DEBUG)

# fh = logging.FileHandler("tele-acp.log")
# fh.setLevel(logging.DEBUG)

logging.basicConfig(
    level=logging.INFO,
    handlers=[logging.StreamHandler(), logging.FileHandler("tele-acp.log")],
)
