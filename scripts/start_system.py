#!/usr/bin/env python3
"""本地一键启动器与简单监控页。"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PROJECT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_DIR / 'src'
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from mine_sensor_secure_comm.config_loader import load_sensor_config  # noqa: E402
from mine_sensor_secure_comm.log_records import LogRecorder  # noqa: E402

WEB_DIR = PROJECT_DIR / 'web'
DEFAULT_WEB_PORT = 8000
MAX_LOG_LINES = 200
MAX_ALERTS = 100
DEFAULT_LOG_FILE = 'logs/launcher.jsonl'


def load_sensor_catalog(sensor_config_path: Path) -> dict[str, dict[str, Any]]:
    """Load configured sensors with metadata used by the dashboard."""
    payload = load_sensor_config(sensor_config_path)
    if not isinstance(payload, dict):
        raise ValueError(f"invalid sensor config object in {sensor_config_path}")
    sensors = payload.get('sensors', {})
    if not isinstance(sensors, dict):
        raise ValueError(f"invalid sensors section in {sensor_config_path}")
    thresholds = payload.get('thresholds', {})
    if not isinstance(thresholds, dict):
        thresholds = {}

    catalog: dict[str, dict[str, Any]] = {}
    for sensor_id, sensor in sensors.items():
        if not isinstance(sensor, dict):
            raise ValueError(f"invalid sensor entry for {sensor_id}")
        sensor_type = str(sensor.get('type', 'unknown'))
        sensor_thresholds = thresholds.get(sensor_type, {})
        if not isinstance(sensor_thresholds, dict):
            sensor_thresholds = {}
        catalog[str(sensor_id)] = {
            'sensor_id': str(sensor_id),
            'sensor_type': sensor_type,
            'unit': str(sensor.get('unit', '')),
            'location': str(sensor.get('location', '')),
            'interval_seconds': float(sensor.get('interval_seconds', 1.0)),
            'thresholds': sensor_thresholds,
        }
    return catalog


def load_sensor_ids(sensor_config_path: Path) -> list[str]:
    """Load all sensor IDs from sensor configuration."""
    return list(load_sensor_catalog(sensor_config_path).keys())


def select_mosquitto_config(project_dir: Path, explicit_path: str | None) -> Path:
    """选择 Mosquitto 配置文件。"""
    if explicit_path:
        return (project_dir / explicit_path).resolve() if not Path(explicit_path).is_absolute() else Path(explicit_path)
    default_path = project_dir / 'config' / 'mosquitto.conf'
    if default_path.exists():
        return default_path
    return project_dir / 'config' / 'mosquitto.conf'


def select_config_with_example(project_dir: Path, explicit_path: str, example_suffix: str) -> Path:
    """选择正式配置，不存在时回退到示例配置。"""
    config_path = (project_dir / explicit_path).resolve() if not Path(explicit_path).is_absolute() else Path(explicit_path)
    if config_path.exists():
        return config_path
    example_path = Path(str(config_path) + example_suffix)
    if example_path.exists():
        return example_path
    raise FileNotFoundError(config_path)


def with_project_pythonpath(env: dict[str, str]) -> dict[str, str]:
    """为子进程补上 src 目录。"""
    new_env = env.copy()
    pythonpath = new_env.get('PYTHONPATH')
    src_dir = str(PROJECT_DIR / 'src')
    if pythonpath:
        new_env['PYTHONPATH'] = src_dir + os.pathsep + pythonpath
    else:
        new_env['PYTHONPATH'] = src_dir
    return new_env


@dataclass
class ManagedProcess:
    """运行中的子进程记录。"""

    name: str
    kind: str
    command: list[str]
    process: subprocess.Popen[str]
    started_at: float
    lines_seen: int = 0

    def snapshot(self) -> dict[str, Any]:
        """返回当前进程状态快照。"""
        return {
            'name': self.name,
            'kind': self.kind,
            'pid': self.process.pid,
            'running': self.process.poll() is None,
            'returncode': self.process.poll(),
            'command': self.command,
            'started_at': self.started_at,
            'lines_seen': self.lines_seen,
        }


@dataclass
class LauncherState:
    """启动器共享状态。"""

    sensor_ids: list[str]
    sensor_catalog: dict[str, dict[str, Any]]
    sensor_config: str
    psk_config: str
    mosquitto_config: str
    web_port: int
    started_at: float = field(default_factory=time.time)
    processes: list[ManagedProcess] = field(default_factory=list)
    log_recorder: LogRecorder = field(default_factory=lambda: LogRecorder(max_lines=MAX_LOG_LINES))
    readings: dict[str, dict[str, Any]] = field(default_factory=dict)
    alerts: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=MAX_ALERTS))

    def add_log(self, source: str, line: str) -> None:
        """追加一条日志。"""
        record = self.log_recorder.append(source, line)
        if source == 'center':
            self.ingest_center_line(record['line'])

    def ingest_center_line(self, line: str) -> None:
        """Ingest one JSON line emitted by the center process."""
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return
        if not isinstance(payload, dict):
            return

        sensor_id = self._sensor_id_from_topic(str(payload.get('topic', '')))
        plaintext = payload.get('plaintext')
        if isinstance(plaintext, dict):
            sensor_id = str(plaintext.get('sensor_id') or sensor_id)
            if sensor_id:
                self._update_sensor_reading(sensor_id, payload, plaintext)

        alerts = payload.get('alerts')
        if isinstance(alerts, list):
            for alert in alerts:
                if isinstance(alert, dict):
                    self._append_alert(alert)

    def _update_sensor_reading(
            self,
            sensor_id: str,
            payload: dict[str, Any],
            plaintext: dict[str, Any],
    ) -> None:
        """Update latest reading or status for one sensor."""
        existing = self.readings.get(sensor_id, {})
        status = plaintext.get('status')
        reading = {
            **existing,
            'sensor_id': sensor_id,
            'accepted': bool(payload.get('accepted', True)),
            'updated_at': time.strftime('%H:%M:%S'),
        }
        if status in {'online', 'offline'}:
            reading['status'] = status
        else:
            reading.update({
                'status': 'online',
                'value': plaintext.get('value'),
                'unit': plaintext.get('unit', self.sensor_catalog.get(sensor_id, {}).get('unit', '')),
                'battery': plaintext.get('battery'),
                'location': plaintext.get('location', self.sensor_catalog.get(sensor_id, {}).get('location', '')),
                'sample_time_ms': plaintext.get('sample_time_ms'),
            })
        self.readings[sensor_id] = reading

    def _append_alert(self, alert: dict[str, Any]) -> None:
        """Append a normalized alert for the notification history."""
        sensor_id = str(alert.get('sensor_id', 'unknown'))
        details = alert.get('details')
        self.alerts.append({
            'ts': time.strftime('%H:%M:%S'),
            'sensor_id': sensor_id,
            'severity': str(alert.get('severity', 'unknown')),
            'code': str(alert.get('code', 'unknown')),
            'message': str(alert.get('message', '')),
            'details': details if isinstance(details, dict) else {},
        })
        if sensor_id in self.readings:
            self.readings[sensor_id]['last_alert'] = str(alert.get('code', 'unknown'))
            self.readings[sensor_id]['last_alert_severity'] = str(alert.get('severity', 'unknown'))

    def _sensor_id_from_topic(self, topic: str) -> str:
        """Extract sensor ID from mine/<sensor_id>/data or status topic."""
        parts = topic.split('/')
        if len(parts) >= 3 and parts[0] == 'mine':
            return parts[1]
        return ''

    def snapshot(self) -> dict[str, Any]:
        """导出前端轮询使用的状态。"""
        sensor_snapshots = []
        running_sensor_ids = {
            item.name
            for item in self.processes
            if item.kind == 'sensor' and item.process.poll() is None
        }
        for sensor_id in self.sensor_ids:
            base = self.sensor_catalog.get(sensor_id, {'sensor_id': sensor_id})
            latest = self.readings.get(sensor_id, {})
            status = latest.get('status')
            if status is None:
                status = 'running' if sensor_id in running_sensor_ids else 'unknown'
            sensor_snapshots.append({
                **base,
                **latest,
                'status': status,
            })
        return {
            'platform': sys.platform,
            'started_at': self.started_at,
            'uptime_seconds': int(time.time() - self.started_at),
            'web_port': self.web_port,
            'sensor_ids': self.sensor_ids,
            'sensors': sensor_snapshots,
            'alerts': list(self.alerts),
            'config': {
                'sensor_config': self.sensor_config,
                'psk_config': self.psk_config,
                'mosquitto_config': self.mosquitto_config,
            },
            'components': [item.snapshot() for item in self.processes],
            'logs': self.log_recorder.snapshot(),
        }

    def frontend_sensor_map(self) -> dict[str, dict[str, Any]]:
        """Build the legacy frontend sensor map from current launcher state."""
        sensors = self.snapshot()['sensors']
        result: dict[str, dict[str, Any]] = {}
        for sensor in sensors:
            sensor_id = str(sensor.get('sensor_id', 'unknown'))
            value = sensor.get('value')
            sensor_type = str(sensor.get('sensor_type', '')).lower()
            unit = str(sensor.get('unit', '')).lower()
            is_temperature = 'temp' in sensor_type or unit in {'c', '°c'}
            is_gas = 'gas' in sensor_type or 'lel' in unit or unit == '%'
            display_value = value if value is not None else '--'
            result[sensor_id] = {
                **sensor,
                'last_temperature': display_value if is_temperature else '--',
                'last_gas': display_value if is_gas else '--',
            }
        return result


def build_mosquitto_command(config_path: Path) -> list[str]:
    """构建 Mosquitto 启动命令。"""
    script_path = PROJECT_DIR / 'scripts' / 'start_mosquitto.bat'
    if os.name == 'nt':
        return ['cmd.exe', '/c', str(script_path), str(config_path)]
    return ['bash', str(PROJECT_DIR / 'scripts' / 'start_mosquitto.sh'), str(config_path)]


def build_center_command(sensor_config: Path, psk_config: Path, host: str | None, port: int | None) -> list[str]:
    """构建地面中心命令。"""
    command = [
        sys.executable,
        '-m',
        'mine_sensor_secure_comm.center',
        '--sensor-config',
        str(sensor_config),
        '--psk-config',
        str(psk_config),
    ]
    if host:
        command.extend(['--host', host])
    if port is not None:
        command.extend(['--port', str(port)])
    return command


def build_sensor_command(
        sensor_id: str,
        sensor_config: Path,
        psk_config: Path,
        host: str | None,
        port: int | None,
) -> list[str]:
    """构建单个传感器命令。"""
    command = [
        sys.executable,
        '-m',
        'mine_sensor_secure_comm.sensor_cli',
        '--sensor-id',
        sensor_id,
        '--sensor-config',
        str(sensor_config),
        '--psk-config',
        str(psk_config),
    ]
    if host:
        command.extend(['--host', host])
    if port is not None:
        command.extend(['--port', str(port)])
    return command


def start_process(name: str, kind: str, command: list[str], state: LauncherState) -> ManagedProcess:
    """启动一个子进程并接管日志。"""
    env = with_project_pythonpath(os.environ)
    creationflags = 0
    if os.name == 'nt':
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
    process = subprocess.Popen(
        command,
        cwd=PROJECT_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        creationflags=creationflags,
    )
    managed = ManagedProcess(
        name=name,
        kind=kind,
        command=command,
        process=process,
        started_at=time.time(),
    )
    state.processes.append(managed)

    def reader() -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            managed.lines_seen += 1
            state.add_log(name, line)

    threading.Thread(target=reader, daemon=True).start()
    state.add_log('launcher', f"started {name}: {' '.join(command)}")
    return managed


def stop_processes(state: LauncherState) -> None:
    """停止全部子进程。"""
    for item in reversed(state.processes):
        process = item.process
        if process.poll() is not None:
            continue
        try:
            process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        except OSError:
            continue


class DashboardHandler(BaseHTTPRequestHandler):
    """提供简单状态 API 和静态页面。"""

    launcher_state: LauncherState

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == '/api/status':
            self._send_json(self.launcher_state.snapshot())
            return
        if parsed.path == '/api/sensors':
            self._send_json(self.launcher_state.frontend_sensor_map())
            return
        self._serve_static(parsed.path)

    def _serve_static(self, request_path: str) -> None:
        if request_path == '/':
            file_path = WEB_DIR / 'index.html'
        else:
            file_path = (WEB_DIR / request_path.lstrip('/')).resolve()
        if not str(file_path).startswith(str(WEB_DIR.resolve())) or not file_path.exists() or file_path.is_dir():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        mime_type, _ = mimetypes.guess_type(file_path.name)
        content_type = mime_type or 'application/octet-stream'
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-Type', f'{content_type}; charset=utf-8')
        self.end_headers()
        self.wfile.write(file_path.read_bytes())

    def _send_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_dashboard(state: LauncherState, open_browser: bool) -> ThreadingHTTPServer:
    """启动本地监控页。"""
    handler_class = type(
        'BoundDashboardHandler',
        (DashboardHandler,),
        {'launcher_state': state},
    )
    server = ThreadingHTTPServer(('127.0.0.1', state.web_port), handler_class)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{state.web_port}"
    state.add_log('launcher', f'dashboard ready at {url}')
    if open_browser:
        try:
            webbrowser.open(url)
        except OSError:
            state.add_log('launcher', 'failed to open browser automatically')
    return server


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description='矿井通信系统一键启动器')
    parser.add_argument('--all', action='store_true', help='启动 Mosquitto、地面中心、全部传感器和监控页')
    parser.add_argument('--mosquitto', action='store_true', help='启动 Mosquitto')
    parser.add_argument('--center', action='store_true', help='启动地面中心')
    parser.add_argument('--all-sensors', action='store_true', help='启动配置中的全部传感器')
    parser.add_argument('--sensor-id', action='append', default=[], help='启动指定传感器，可重复传入')
    parser.add_argument('--web', action='store_true', help='启动本地监控页')
    parser.add_argument('--no-browser', action='store_true', help='启动监控页时不自动打开浏览器')
    parser.add_argument('--web-port', type=int, default=DEFAULT_WEB_PORT, help='监控页端口，默认 8000')
    parser.add_argument('--sensor-config', default='config/sensors.toml', help='传感器配置文件路径')
    parser.add_argument('--psk-config', default='config/psk.json', help='PSK 配置文件路径')
    parser.add_argument('--mosquitto-config', default=None, help='Mosquitto 配置文件路径')
    parser.add_argument(
        '--log-file',
        default=DEFAULT_LOG_FILE,
        help='启动器 JSONL 日志文件路径，默认 logs/launcher.jsonl',
    )
    parser.add_argument('--host', default=None, help='覆盖 MQTT 主机地址')
    parser.add_argument('--port', type=int, default=None, help='覆盖 MQTT 端口')
    return parser.parse_args()


def main() -> int:
    """运行启动器主流程。"""
    args = parse_args()
    if args.all:
        args.mosquitto = True
        args.center = True
        args.all_sensors = True
        args.web = True

    if not any([args.mosquitto, args.center, args.all_sensors, args.sensor_id, args.web]):
        print('未指定启动项，请使用 --all 或至少选择一个组件。')
        return 1

    sensor_config_path = select_config_with_example(PROJECT_DIR, args.sensor_config, '.example')
    psk_config_path = select_config_with_example(PROJECT_DIR, args.psk_config, '.example')
    mosquitto_config_path = select_mosquitto_config(PROJECT_DIR, args.mosquitto_config)
    log_file_path = (
        (PROJECT_DIR / args.log_file).resolve()
        if not Path(args.log_file).is_absolute()
        else Path(args.log_file)
    )

    sensor_catalog = load_sensor_catalog(sensor_config_path)
    configured_sensor_ids = list(sensor_catalog.keys())
    selected_sensor_ids = list(args.sensor_id)
    if args.all_sensors:
        selected_sensor_ids = configured_sensor_ids

    state = LauncherState(
        sensor_ids=configured_sensor_ids,
        sensor_catalog=sensor_catalog,
        sensor_config=str(sensor_config_path),
        psk_config=str(psk_config_path),
        mosquitto_config=str(mosquitto_config_path),
        web_port=args.web_port,
        log_recorder=LogRecorder(max_lines=MAX_LOG_LINES, log_path=log_file_path),
    )

    dashboard = None
    try:
        if args.web:
            dashboard = start_dashboard(state, open_browser=not args.no_browser)
        if args.mosquitto:
            start_process('mosquitto', 'broker', build_mosquitto_command(mosquitto_config_path), state)
            time.sleep(1.0)
        if args.center:
            start_process(
                'center',
                'center',
                build_center_command(sensor_config_path, psk_config_path, args.host, args.port),
                state,
            )
            time.sleep(1.0)
        for sensor_id in selected_sensor_ids:
            start_process(
                sensor_id,
                'sensor',
                build_sensor_command(sensor_id, sensor_config_path, psk_config_path, args.host, args.port),
                state,
            )
            time.sleep(0.3)

        print('launcher started; press Ctrl+C to stop all child processes')
        if args.web:
            print(f"dashboard: http://127.0.0.1:{args.web_port}")
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print('\nstopping launcher...')
    finally:
        if dashboard is not None:
            dashboard.shutdown()
            dashboard.server_close()
        stop_processes(state)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
