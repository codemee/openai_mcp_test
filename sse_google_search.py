from mcp.server.fastmcp import FastMCP
from googlesearch import search
from starlette.applications import Starlette
from starlette.routing import Mount

mcp = FastMCP(
    "shell_helper",
    host='0.0.0.0'
)

@mcp.tool()
async def google_res(keyword: str, num_results: int = 5) -> str:
    """使用 Google 搜尋關鍵字，並回傳搜尋結果
    Args:
        keyword (str): 搜尋關鍵字
        num_results (int): 搜尋結果數量，預設為 5 筆
    """
    content = ""
    num_results = max(num_results, 5) # 最少 5 筆
    for result in search( # 一一串接搜尋結果
        keyword,
        advanced=True,
        num_results=num_results,
        lang='zh-TW'
    ):
        # 使用 markdown 格式整理搜尋結果
        content += (f"- [{result.title}]({result.url})\n"
                    f"    {result.description}\n")
    return content

# app = Starlette(
#     routes=[
#         Mount('/', mcp.sse_app()),
#     ]
# )
    
if __name__ == "__main__":
    # 執行伺服器
    mcp.run(transport='sse')