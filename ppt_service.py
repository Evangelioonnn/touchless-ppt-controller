"""Bounded PowerPoint worker. COM lives only on its owning thread."""
from __future__ import annotations

import logging
import queue
import threading
import time

from command_gate import Command, CommandGate
from powerpoint_bridge import OperationResult, PowerPointBridge, PowerPointStatus


class PowerPointService:
    def __init__(self, gate: CommandGate, backend: str = 'keys', bridge_factory=PowerPointBridge):
        self.gate, self.backend, self.bridge_factory = gate, backend, bridge_factory
        self.commands: queue.Queue = queue.Queue(maxsize=1)
        self.controls: queue.Queue = queue.Queue(maxsize=16)
        self.results: queue.Queue = queue.Queue(maxsize=16)
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.current = PowerPointStatus(False, 'Searching for PowerPoint', False)
        self.busy = False
        self.thread = threading.Thread(target=self._run, name='powerpoint', daemon=True)

    def start(self):
        self.thread.start()

    def submit(self, command: Command) -> bool:
        try:
            self.commands.put_nowait(command)
            return True
        except queue.Full:
            return False

    def control(self, action: str, value=None) -> None:
        if action in ('target', 'backend'):
            self.gate.invalidate()
        try:
            self.controls.put_nowait((action, value))
        except queue.Full:
            logging.getLogger('touchless').warning('PPT control queue full')

    def status(self) -> PowerPointStatus:
        with self.lock:
            return self.current

    def _result(self, result: OperationResult) -> None:
        try:
            self.results.put_nowait(result)
        except queue.Full:
            self.results.get_nowait()
            self.results.put_nowait(result)

    def _run(self) -> None:
        pythoncom = None
        try:
            try:
                import pythoncom as com
                com.CoInitialize()
                pythoncom = com
            except ImportError:
                pass
            bridge = self.bridge_factory(backend=self.backend)
            while not self.stop_event.is_set():
                try:
                    action, value = self.controls.get_nowait()
                    if action == 'refresh':
                        bridge.refresh()
                    elif action == 'target':
                        bridge.select_target(str(value))
                    elif action == 'backend':
                        bridge.backend = str(value)
                    elif action == 'start':
                        self.busy = True
                        try:
                            self._result(bridge.start_slideshow())
                        finally:
                            self.busy = False
                        bridge.refresh()
                except queue.Empty:
                    pass
                status = bridge.refresh_if_needed(time.perf_counter())
                with self.lock:
                    self.current = status
                try:
                    command = self.commands.get(timeout=0.03)
                except queue.Empty:
                    continue
                if self.gate.valid(command) and status.connected and command.target == status.target_id:
                    self.busy = True
                    try:
                        if self.gate.valid(command):
                            self._result(bridge.execute(command.action))
                    finally:
                        self.busy = False
        except Exception as error:
            logging.getLogger('touchless').exception('PowerPoint worker failed')
            self.gate.invalidate()
            with self.lock:
                self.current = PowerPointStatus(False, 'PowerPoint control unavailable', False, message=str(error))
        finally:
            if pythoncom is not None:
                pythoncom.CoUninitialize()

    def close(self) -> bool:
        self.gate.invalidate()
        self.stop_event.set()
        self.thread.join(2)
        return not self.thread.is_alive()
