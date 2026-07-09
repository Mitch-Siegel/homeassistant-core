import sys
import asyncio 
import json

AMPLIFIER_PORT = 6790


class ApexAmplifierError(Exception):
    """Exception raised when an APEX amplifier returns a status other than OK."""
    pass

class ApexStatusError(Exception):
    """Exception raised when an APEX amplifier returns a status other than OK."""
    pass

class ApexConnectionError(Exception):
    """Exception raised when a connection to an APEX Cloudpower amplifier fails"""

# Single listener, since all amp responses are sent to 6790 irrespective of request origin port
class SharedAmplifierListener(asyncio.DatagramProtocol):
    def __init__(self):
        self.transport = None
        self.pending_requests: Dict[str, list[asyncio.Future]] = {}

    def enqueue_request(self, ip: str) -> asyncio.future:

        future = asyncio.get_running_loop().create_future()

        if not ip in self.pending_requests:
            self.pending_requests[ip] = []

        self.pending_requests[ip].append(future)

        return future

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr):
        ip, port = addr
        # Route response to first future waiting on this IP
        if ip in self.pending_requests:
            future = self.pending_requests[ip].pop(0)
            if not future.done():
                future.set_result(data)

    def error_received(self, exc):
        print(f"Global Listener Error: {exc}")
        for requests in self.pending_requests.values():
            for future in requests:
                if not future.done():
                    future.set_exception(exc)

"""Manages the shared network port socket lifecycle and clients."""
class CloudpowerManager:
    def __init__(self):
        self.listener: SharedAmplifierListener = None
        self.transport = None

    async def start(self):
        loop = asyncio.get_running_loop()
        self.listener = SharedAmplifierListener()
        
        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: self.listener,
            local_addr=('0.0.0.0', AMPLIFIER_PORT),
            reuse_port=True
        )
        print(f"Global Shared Listener active on local port {AMPLIFIER_PORT}")

    def get_client(self, ip: str) -> 'CloudpowerClient':
        """Factory method to get a client hooked into this shared manager"""
        if not self.listener:
            raise RuntimeError("Manager must be started with 'await manager.start()' first.")
        return CloudpowerClient(ip, self)

    def close(self):
        """Shuts down the socket connection"""
        if self.transport:
            self.transport.close()


# TODO: implement stop
class CloudpowerClient:
    def __init__(self, ip: str, manager: CloudpowerManager):
        self.ip = ip
        self.port = AMPLIFIER_PORT  # Remote amplifier port
        self.manager = manager

    async def send_cmd(self, payload: dict, timeout: float = 1.0):
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        # TODO: fix possibility of race with ordering between here and tx of message
        future = self.manager.listener.enqueue_request(self.ip)

        json_message = json.dumps(payload)
        self.manager.transport.sendto(json_message.encode('utf-8'), (self.ip, self.port))
        print(f"[{self.ip}] Sent: {json_message}")

        try:
            data = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            print(f"[{self.ip}] Error: No response from amplifier.")
            raise ApexConnectionError(f"Connection timed out waiting for {self.ip}")

        # Process JSON response data from janky APEX format
        response_text = data.decode('utf-8')
        try:
            resp_json = json.loads(response_text)
            status = resp_json.get("status")
            resp_data = resp_json.get("response")

            if status == "OK":
                print(f"[{self.ip}] Received: {resp_data}")
                return resp_data
            else:
                raise ApexAmplifierError(f"[{self.ip}] Error status: {resp_data}")
        except json.JSONDecodeError:
            print(f"[{self.ip}] Error: Non-JSON payload received: {response_text}")
            raise

    async def get_standby(self, timeout: float = 1.0):
        return await self.send_cmd({"command": "get_standby_status"}, timeout=timeout)

    async def set_standby(self, enable: bool, timeout: float = 1.0):
        return await self.send_cmd({"command": "set_standby_status", "arg1": enable}, timeout=timeout)

    async def get_amplifier_status(self, timeout: float = 1.0):
        return await self.send_cmd({"command": "get_amplifier_status"}, timeout=timeout)
 
    async def get_module_temperature(self):
        return await self.send_cmd({"command": "get_module_temperature"})

    

