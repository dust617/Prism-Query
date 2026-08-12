@echo off
rem SearchBrain MCP server 启动器（确保能找到 searchbrain 包）
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python -m searchbrain.mcp_server