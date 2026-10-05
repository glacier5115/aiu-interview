"""CLI 交互层。

负责：读用户输入、把斜杠命令翻译成动作、订阅客户端产出的文本块并渲染、
再把结果写回会话状态。

终端相关的交互全部集中在这个模块里。核心的通信与状态都在顶层的
``shared.llm_chat`` 包里，不依赖本模块，所以换一种应用形态（例如 Web）
时替换掉这一层即可。
"""

from __future__ import annotations

from shared.llm_chat.client import OllamaClient, OllamaError
from shared.llm_chat.session import ConversationSession

from . import terminal

HELP_TEXT = """可用命令：
  /help            显示本帮助
  /clear           清空对话上下文（保留 system prompt）
  /model [名称]    切换模型；不带名称时列出本机可用模型
  /exit            退出程序（/quit、/q 同效）
"""


def run(client: OllamaClient, session: ConversationSession) -> None:
    """交互式对话主循环。"""
    print(f"已连接 {client.host}，当前模型 {client.model}")
    print("输入 /help 查看命令，/exit 退出\n")

    while True:
        try:
            user_input = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not user_input:
            continue

        if user_input.startswith("/"):
            if _handle_command(user_input, client, session) == "exit":
                return
            continue

        _reply_once(client, session, user_input)


def _reply_once(client: OllamaClient, session: ConversationSession, user_input: str) -> None:
    """完成一轮问答：写入提问、流式渲染回复、把回复写回上下文。"""
    session.add_user(user_input)
    print(f"{client.model} > ", end="", flush=True)

    pieces: list[str] = []
    try:
        for piece in client.chat_stream(session.messages):
            pieces.append(piece)
            print(terminal.sanitize(piece), end="", flush=True)
    except OllamaError as exc:
        print(f"\n[错误] {exc}\n")
        session.drop_last()
        return
    except KeyboardInterrupt:
        print("\n[已中断本轮回复]\n")
        session.drop_last()
        return

    if not pieces:
        print("\n[警告] 模型没有返回正文。可能是思考内容占满了输出配额，"
              "可加 --think 参数观察完整思考过程。\n")
        session.drop_last()
        return

    print("\n")
    session.add_assistant("".join(pieces))


def _handle_command(line: str, client: OllamaClient, session: ConversationSession) -> str:
    """处理以 / 开头的命令。返回 "exit" 表示要退出程序。"""
    command, _, argument = line[1:].partition(" ")
    command = command.lower()
    argument = argument.strip()

    if command in ("exit", "quit", "q"):
        return "exit"

    if command == "clear":
        session.clear()
        print("[已清空对话上下文]\n")
    elif command == "model":
        _switch_model(argument, client)
    elif command == "help":
        print(HELP_TEXT)
    else:
        print(f"未知命令 /{command}，输入 /help 查看可用命令\n")

    return "ok"


def _switch_model(argument: str, client: OllamaClient) -> None:
    """切换模型；不带参数时列出本机可用模型。"""
    if argument:
        client.model = argument
        print(f"[已切换模型：{argument}]\n")
        return

    try:
        names = client.list_models()
    except OllamaError as exc:
        print(f"[错误] {exc}\n")
        return

    print("本机可用模型：")
    for name in names:
        marker = "*" if name == client.model else " "
        print(f"  {marker} {name}")
    print()
