import time

from agentize_bridge import AgentizeServer

server = AgentizeServer()


@server.command(thread="worker")
def add(a: int, b: int) -> int:
    """ 把两个数字相加 """
    return a + b


@server.command(thread="main", timeout=5)
def get_state() -> dict:
    """ 读取只能在主线程访问的应用状态 """
    return {"ready": True}


if __name__ == "__main__":
    server.start_http(host="127.0.0.1", port=8765)
    try:
        while True:
            server.run_pending()
            time.sleep(0.01)
    except KeyboardInterrupt:
        server.close()
