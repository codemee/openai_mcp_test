import asyncio
from typing import Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# from anthropic import Anthropic
from openai import OpenAI

from rich.pretty import pprint
import os

class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        # self.anthropic = Anthropic()
        self.openai = OpenAI()

    # methods will go here

    async def connect_to_server(self, server_script_path: str):
        """Connect to an MCP server

        Args:
            server_script_path: Path to the server script (.py or .js)
        """

        abs_path = os.path.abspath(server_script_path)
        path = os.path.dirname(abs_path)
        script = os.path.basename(abs_path)
        env = {} 
        if 'spotify' in script.lower():
            # Spotify API requires environment variables
            env = {
                "SPOTIFY_CLIENT_ID": os.getenv("SPOTIFY_CLIENT_ID"),
                "SPOTIFY_CLIENT_SECRET": os.getenv("SPOTIFY_CLIENT_SECRET")
            }

        server_params = StdioServerParameters(
            # 在 Linux 上最好寫完整的路徑
            # 因為 Linux 是以 env 參數內的 PATH 搜尋可執行檔
            # 但底下會把 env 清掉不會有 PATH 提供搜尋路徑
            # Windows 上會以目前環境的 PATH 搜尋不會有問題
            command='uv',
            # 你可以把路徑放在 uv 的 --directory 參數
            # 讓 uv 切換工作目錄再執行 script
            # 官方範例都是採用上述這種作法
            # args=['run', '--directory', path, script],
            
            # 或是也可以像是這樣利用 cwd 指定 server 路徑
            # SDK 會先切換工作目錄才執行 command
            # 如果不是使用 uv 執行 python 就需要這種方式
            args=['run', script],
            cwd=path,

            # 建立 server 執行時的環境變數
            # 如果不設定，預設是 None，會傳遞所有的環境變數
            # 設為 {} 則完全不傳遞本機的環境變數
            # client 應該只傳遞 server 執行所需的環境變數
            # 這樣在 server 中就取不到其他環境變數內容
            # 避免洩漏本機環境變數給 server 的風險
            env=env
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

        # List available tools
        response = await self.session.list_tools()
        tools = response.tools
        print("\nConnected to server with tools:", [tool.name for tool in tools])
        # pprint(tools)

    async def process_query(self, query: str, hist: list) -> str:
        """Process a query using llm and available tools"""
        messages = hist + [
            {
                "role": "user",
                "content": query
            }
        ]

        response = await self.session.list_tools()
        available_tools = [{
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.inputSchema
        } for tool in response.tools]

        while True:
            # Initial Claude API call
            response = self.openai.responses.create(
                # model="claude-3-5-sonnet-20241022",
                model="gpt-4o-mini",
                # max_tokens=1000,
                input=messages,
                tools=available_tools
            )

            # Process response and handle tool calls
            tool_results = []
            final_text = []

            assistant_message_content = []
            for output in response.output:
                if output.type == 'message':
                    final_text.append(output.content[0].text)
                    assistant_message_content.append(output.content[0].text)
                elif output.type == 'function_call':
                    # pprint(output)
                    tool_name = output.name
                    tool_args = eval(output.arguments)

                    # Execute tool call
                    result = await self.session.call_tool(tool_name, tool_args)
                    tool_results.append({"call": tool_name, "result": result})
                    final_text.append(
                        f"\n[Calling tool {tool_name} with args {tool_args}]\n\n"
                        f"{result.content[0].text}\n\n"
                    )

                    assistant_message_content.append(output)
                    messages.append(output)
                    messages.append({
                        # 建立可傳回函式執行結果的字典
                        "type": "function_call_output", # 以工具角色送出回覆
                        "call_id": output.call_id, # 叫用函式的識別碼
                        "output": result.content[0].text # 函式傳回值
                    })
            if tool_results == []:
                break
        return "\n".join(final_text)

    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")

        hist = []
        while True:
            try:
                pprint(hist)
                query = input("\nQuery: ").strip()

                if query.lower() == 'quit':
                    break

                response = await self.process_query(query, hist)
                print("\n" + response)
                hist += [{"role": "user", "content": query}]
                hist += [{"role": "assistant", "content": response}]

            except Exception as e:
                print(f"\nError: {str(e)}")

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()

async def main():
    if len(sys.argv) < 2:
        print("Usage: python client.py <path_to_server_script>")
        sys.exit(1)

    client = MCPClient()
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    import sys
    asyncio.run(main())

