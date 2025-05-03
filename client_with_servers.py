from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack
from openai import OpenAI
import asyncio
import json
import sys
import os

openai = OpenAI()

class MCPClient:
    def __init__(self):
        self.session = None
        self.exit_stack = AsyncExitStack()
        self.tools = []
        self.tool_names = []

    async def connect_to_server(self, server_info):
        """連接 MCP 伺服器

        Args:
            server_info: MCP 伺服器的連接資訊
        """

        server_params = StdioServerParameters(**server_info[1])

        stdio_transport = await (
            self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
        )
        self.stdio, self.write = stdio_transport
        self.session = await (
            self.exit_stack.enter_async_context(
                ClientSession(self.stdio, self.write)
            )
        )

        await self.session.initialize()

        # List available tools
        response = await self.session.list_tools()
        tools = response.tools
        self.tools = [{
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.inputSchema
        } for tool in tools]
        self.tool_names = [tool.name for tool in tools]
        
        print('-' * 20)
        print(f"已連接 {server_info[0]} 伺服器")
        print('\n'.join(
            [f'    - {name}' for name in self.tool_names]
        ))
        print('-' * 20)

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()

async def get_reply_text(clients, query, hist):
    """單次問答"""
    
    # 自行處理對話記錄
    messages = hist + [{"role": "user", "content": query}]
    # 把 clients 中個別項目的 tools 串接在一起
    tools = []
    for client in clients:
        tools += client.tools

    while True:
        # 使用 Responses API 請 LLM 生成回覆
        response = openai.responses.create(
            # model="gpt-4.1-mini",
            model="gpt-4.1",
            input=messages,
            tools=tools,
            store=False # 不儲存對話紀錄
        )

        # Process response and handle tool calls
        tool_results = []
        final_text = []

        for output in response.output:
            if output.type == 'message': # 一般訊息
                final_text.append(output.content[0].text)
            elif output.type == 'function_call': # 使用工具
                tool_name = output.name
                tool_args = eval(output.arguments)
                for client in clients:
                    if tool_name in client.tool_names:
                        break
                else:
                    # 如果沒有找到對應的工具，則跳過這個迴圈
                    continue
                print(f"準備使用 {tool_name}(**{tool_args})")
                print('-' * 20)
                # 使用 MCP 伺服器提供的工具
                result = await client.session.call_tool(
                    tool_name, tool_args
                )
                tool_results.append(
                    {"call": tool_name, "result": result}
                )
                print(f"{result.content[0].text}")
                print('-' * 20)

                messages.append(output)
                messages.append({
                    # 建立可傳回函式執行結果的字典
                    "type": "function_call_output", # 設為工具輸出類型的訊息
                    "call_id": output.call_id, # 叫用函式的識別碼
                    "output": result.content[0].text # 函式傳回值
                })
        if tool_results == []:
            break
    return "\n".join(final_text)

async def chat_loop(clients):
    """聊天迴圈"""
    print("直接按 ↵ 可結束對話")

    hist = []
    while True:
        try:
            query = input(">>> ").strip()

            if query == '':
                break

            reply = await get_reply_text(
                clients, query, hist
            )
            print(reply)
            hist += [{"role": "user", "content": query}]
            hist += [{"role": "assistant", "content": reply}]
            hist = hist[-6:] # 只保留最近的 10 筆對話紀錄

        except Exception as e:
            print(f"\nError: {str(e)}")

async def main():
    if (not os.path.exists("mcp_servers.json") or
        not os.path.isfile("mcp_servers.json")):
        print("Error:找不到 mcp_servers.json 檔", file=sys.stderr)
        return
    
    with open("mcp_servers.json", "r", encoding="utf-8") as f:
        try:
            server_infos = tuple(
                json.load(f)['mcpServers'].items()
            )
        except:
            print(
                "Error: mcp_servers.json 檔案格式錯誤", 
                file=sys.stderr
            )
            return
    
    if len(server_infos) == 0:
        print(
            "Error: mcp_servers.json 檔案內沒有任何伺服器", 
            file=sys.stderr
        )
        return
    
    clients = []
    try:
        for server_info in server_infos:
            client = MCPClient()
            await client.connect_to_server(server_info)
            clients.append(client)
        await chat_loop(clients)
    finally:
        # 反向清除資源，確保所有伺服器都能正常關閉
        for client in clients[::-1]:
            await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())

