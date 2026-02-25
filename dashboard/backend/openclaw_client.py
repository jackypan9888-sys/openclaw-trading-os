"""
OpenClaw Gateway WebSocket Client
用于从 Trading OS 连接到 OpenClaw Agent
"""
import asyncio
import json
import hashlib
import hmac
import time
from typing import Optional, Callable
import websockets

class OpenClawClient:
    def __init__(self, gateway_url: str = "ws://127.0.0.1:18789/rpc", token: str = ""):
        self.gateway_url = gateway_url
        self.token = token
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.request_id = 0
        self.pending_requests = {}
        self.authenticated = False
        
    async def connect(self) -> bool:
        """连接到 Gateway 并完成认证"""
        try:
            headers = [("Authorization", f"Bearer {self.token}")]
            self.ws = await websockets.connect(
                self.gateway_url, 
                additional_headers=headers,
                ping_interval=30
            )
            
            # 等待 challenge
            response = await asyncio.wait_for(self.ws.recv(), timeout=10)
            data = json.loads(response)
            
            if data.get("event") == "connect.challenge":
                nonce = data["payload"]["nonce"]
                ts = data["payload"]["ts"]
                
                # 签名 challenge
                signature = hmac.new(
                    self.token.encode(),
                    f"{nonce}:{ts}".encode(),
                    hashlib.sha256
                ).hexdigest()
                
                # 发送认证响应
                auth_response = {
                    "type": "auth",
                    "nonce": nonce,
                    "ts": ts,
                    "signature": signature
                }
                await self.ws.send(json.dumps(auth_response))
                
                # 等待认证确认
                auth_result = await asyncio.wait_for(self.ws.recv(), timeout=10)
                auth_data = json.loads(auth_result)
                
                if auth_data.get("event") == "connect.authenticated":
                    self.authenticated = True
                    return True
                else:
                    print(f"Auth failed: {auth_data}")
                    return False
            else:
                print(f"Unexpected response: {data}")
                return False
                
        except Exception as e:
            print(f"Connection error: {e}")
            return False
    
    async def send_message(self, message: str, session_id: str = None, agent_id: str = "main") -> Optional[str]:
        """
        发送消息到 OpenClaw Agent 并获取回复
        """
        if not self.authenticated:
            if not await self.connect():
                return None
        
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "agent.chat",
            "params": {
                "message": message,
                "agentId": agent_id,
            }
        }
        
        if session_id:
            request["params"]["sessionId"] = session_id
        
        try:
            await self.ws.send(json.dumps(request))
            
            # 收集响应（可能是流式的）
            full_response = ""
            while True:
                response = await asyncio.wait_for(self.ws.recv(), timeout=120)
                data = json.loads(response)
                
                # 处理不同类型的响应
                if data.get("type") == "event":
                    event = data.get("event", "")
                    if event == "agent.chunk":
                        # 流式响应的一部分
                        chunk = data.get("payload", {}).get("text", "")
                        full_response += chunk
                    elif event == "agent.done":
                        # 响应完成
                        break
                    elif event == "agent.error":
                        return f"Error: {data.get('payload', {}).get('message', 'Unknown error')}"
                elif "result" in data:
                    # 直接响应
                    return data["result"].get("reply", data["result"].get("message", str(data["result"])))
                elif "error" in data:
                    return f"Error: {data['error'].get('message', 'Unknown error')}"
            
            return full_response or None
            
        except asyncio.TimeoutError:
            return "请求超时"
        except Exception as e:
            return f"Error: {str(e)}"
    
    async def close(self):
        """关闭连接"""
        if self.ws:
            await self.ws.close()
            self.ws = None
            self.authenticated = False


# 简单的同步包装器
def send_to_openclaw(message: str, token: str, gateway_url: str = "ws://127.0.0.1:18789/rpc") -> str:
    """
    同步发送消息到 OpenClaw
    """
    async def _send():
        client = OpenClawClient(gateway_url, token)
        try:
            result = await client.send_message(message)
            return result or "无响应"
        finally:
            await client.close()
    
    return asyncio.run(_send())


if __name__ == "__main__":
    # 测试
    import sys
    token = "cc83a5a39fe092421e17ba630a734e6cab89ac79230c4bd50192067b15cd6b28"
    message = sys.argv[1] if len(sys.argv) > 1 else "你好，简短回复：你是谁？"
    
    print(f"Sending: {message}")
    result = send_to_openclaw(message, token)
    print(f"Response: {result}")
