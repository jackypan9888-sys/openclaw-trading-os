"""
OpenClaw 消息队列
通过文件系统实现 Trading OS 与 OpenClaw Agent 的通信
"""
import os
import json
import time
import uuid
from pathlib import Path
from typing import Optional

QUEUE_DIR = Path.home() / ".openclaw" / "trading-os" / "message_queue"
REQUESTS_DIR = QUEUE_DIR / "requests"
RESPONSES_DIR = QUEUE_DIR / "responses"

def init_queue():
    """初始化队列目录"""
    REQUESTS_DIR.mkdir(parents=True, exist_ok=True)
    RESPONSES_DIR.mkdir(parents=True, exist_ok=True)

def send_request(message: str, timeout: int = 60) -> Optional[str]:
    """
    发送请求到 OpenClaw Agent 并等待响应
    
    Args:
        message: 用户消息
        timeout: 超时时间（秒）
    
    Returns:
        Agent 的响应，或 None（超时）
    """
    init_queue()
    
    # 创建请求
    request_id = str(uuid.uuid4())
    request_file = REQUESTS_DIR / f"{request_id}.json"
    
    request_data = {
        "id": request_id,
        "message": message,
        "timestamp": time.time(),
        "status": "pending"
    }
    
    with open(request_file, "w") as f:
        json.dump(request_data, f, ensure_ascii=False)
    
    # 等待响应
    response_file = RESPONSES_DIR / f"{request_id}.json"
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        if response_file.exists():
            try:
                with open(response_file) as f:
                    response_data = json.load(f)
                # 清理文件
                request_file.unlink(missing_ok=True)
                response_file.unlink(missing_ok=True)
                return response_data.get("reply", "")
            except Exception as e:
                return f"Error reading response: {e}"
        time.sleep(0.5)
    
    # 超时，清理请求文件
    request_file.unlink(missing_ok=True)
    return None


def get_pending_requests() -> list:
    """
    获取所有待处理的请求（供 OpenClaw Agent 调用）
    """
    init_queue()
    requests = []
    
    for f in REQUESTS_DIR.glob("*.json"):
        try:
            with open(f) as file:
                data = json.load(file)
                if data.get("status") == "pending":
                    requests.append(data)
        except Exception:
            pass
    
    return sorted(requests, key=lambda x: x.get("timestamp", 0))


def respond_to_request(request_id: str, reply: str):
    """
    回复一个请求（供 OpenClaw Agent 调用）
    """
    init_queue()
    
    # 更新请求状态
    request_file = REQUESTS_DIR / f"{request_id}.json"
    if request_file.exists():
        try:
            with open(request_file) as f:
                data = json.load(f)
            data["status"] = "completed"
            with open(request_file, "w") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass
    
    # 写入响应
    response_file = RESPONSES_DIR / f"{request_id}.json"
    response_data = {
        "id": request_id,
        "reply": reply,
        "timestamp": time.time()
    }
    
    with open(response_file, "w") as f:
        json.dump(response_data, f, ensure_ascii=False)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        
        if cmd == "send" and len(sys.argv) > 2:
            message = sys.argv[2]
            print(f"Sending: {message}")
            reply = send_request(message, timeout=30)
            print(f"Reply: {reply}")
        
        elif cmd == "pending":
            requests = get_pending_requests()
            print(f"Pending requests: {len(requests)}")
            for r in requests:
                print(f"  - {r['id']}: {r['message'][:50]}...")
        
        elif cmd == "respond" and len(sys.argv) > 3:
            request_id = sys.argv[2]
            reply = sys.argv[3]
            respond_to_request(request_id, reply)
            print(f"Responded to {request_id}")
        
        else:
            print("Usage:")
            print("  python openclaw_queue.py send <message>")
            print("  python openclaw_queue.py pending")
            print("  python openclaw_queue.py respond <request_id> <reply>")
    else:
        print("OpenClaw Message Queue")
        init_queue()
        print(f"Queue dir: {QUEUE_DIR}")
