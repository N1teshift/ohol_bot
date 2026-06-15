$ErrorActionPreference = "Stop"

$env:PYTHONPATH = "src"
python -m ohol_bot.cli play @args
