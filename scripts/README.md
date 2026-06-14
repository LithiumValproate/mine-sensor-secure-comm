**在项目根目录下运行**

- `generate_certs.sh` / `generate_certs.bat`
  生成本地测试 CA、Broker、地面中心和示例传感器证书。
- `start_mosquitto.sh` / `start_mosquitto.bat`
  启动使用 mTLS 配置的 Mosquitto，默认优先读取 `config/mosquitto.conf`，不存在时回退到 `.example`。
- `start_system.py`
  跨平台一键启动器，可组合启动 Broker、地面中心、传感器和本地监控页。
- `start_system.bat`
  Windows 下的一键启动入口，等价于运行 `python scripts\start_system.py --all --web`。
- `run_performance_tests.py`
  运行性能测试并导出报告用柱状图，默认输出到 `performance_outputs/`，会生成 `performance_results.csv`、`performance_summary.json`、`latency_by_encryption.png` 和 `throughput_by_sensor_count.png`。
