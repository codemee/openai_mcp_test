from mcp.server.fastmcp import FastMCP
from fastapi import FastAPI

# Initialize the MCP server
app = FastAPI()
mcp = FastMCP("My SSE Server")

# Define a tool
@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b


# Mount the SSE app to your FastAPI application
app.mount("/", mcp.sse_app())
import uvicorn

# 目前似乎 clause desktop 還不支援 sse 通訊的 mcp server
# 但可以用 VSCode 測試
# 先把 server 跑起來 uv run server_sse_add.py
# 然後再 VSCode 的設定中 mcp 的 servers 中加入：
# "test-sse-mcp": {
#    "type": "sse",
#    "url": "http://localhost:8000/sse"
# }

uvicorn.run(app, host="0.0.0.0", port=8000)