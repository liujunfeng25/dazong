import asyncio
from collections import defaultdict
from typing import Dict, Iterable, Set

from fastapi import WebSocket


class WSManager:
    def __init__(self):
        self.monitor_clients: Set[WebSocket] = set()
        self.role_clients: Dict[str, Set[WebSocket]] = defaultdict(set)
        self.role_user_clients: Dict[str, Dict[int, Set[WebSocket]]] = defaultdict(
            lambda: defaultdict(set)
        )
        self._lock = asyncio.Lock()

    async def connect_monitor(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self.monitor_clients.add(ws)

    async def connect_role(self, role: str, user_id: int, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self.role_clients[role].add(ws)
            self.role_user_clients[role][int(user_id)].add(ws)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            if ws in self.monitor_clients:
                self.monitor_clients.remove(ws)
            for role in list(self.role_clients.keys()):
                if ws in self.role_clients[role]:
                    self.role_clients[role].remove(ws)
                if not self.role_clients[role]:
                    self.role_clients.pop(role, None)
            for role in list(self.role_user_clients.keys()):
                for user_id in list(self.role_user_clients[role].keys()):
                    user_sockets = self.role_user_clients[role][user_id]
                    if ws in user_sockets:
                        user_sockets.remove(ws)
                    if not user_sockets:
                        self.role_user_clients[role].pop(user_id, None)
                if not self.role_user_clients[role]:
                    self.role_user_clients.pop(role, None)

    async def broadcast_monitor(self, payload: dict):
        stale = []
        for ws in list(self.monitor_clients):
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001
                stale.append(ws)
        for ws in stale:
            await self.disconnect(ws)

    async def broadcast_role(self, role: str, payload: dict):
        stale = []
        for ws in list(self.role_clients.get(role, set())):
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001
                stale.append(ws)
        for ws in stale:
            await self.disconnect(ws)

    async def broadcast_users(self, role: str, user_ids: Iterable[int], payload: dict):
        stale = []
        role_map = self.role_user_clients.get(role, {})
        for user_id in {int(i) for i in user_ids if i}:
            for ws in list(role_map.get(user_id, set())):
                try:
                    await ws.send_json(payload)
                except Exception:  # noqa: BLE001
                    stale.append(ws)
        for ws in stale:
            await self.disconnect(ws)


ws_manager = WSManager()
