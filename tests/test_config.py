"""config 加载与校验测试。"""
import json

from app.config import AppConfig, InstanceConfig, load_config


def test_default_config_generated(tmp_path):
    cfg_path = tmp_path / "cfg.json"
    cfg = load_config(cfg_path)
    assert cfg.web.port == 8666
    assert cfg.collect_interval == 10
    assert cfg_path.exists()
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert "instances" in raw


def test_validate_and_enabled(tmp_path):
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(
        json.dumps({
            "web": {"port": 9000},
            "instances": [
                {"name": "a", "host": "h", "port": "1", "token": "t", "enabled": True},
                {"name": "b", "host": "h2", "port": "2", "token": "t2", "enabled": False},
            ],
        }),
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)
    assert cfg.web.port == 9000
    assert len(cfg.enabled_instances()) == 1
    assert cfg.enabled_instances()[0].name == "a"


def test_instance_urls():
    inst = InstanceConfig(name="a", host="10.0.0.1", port="1234", token="t")
    assert inst.base_url == "https://10.0.0.1:1234/youlilucky"
    assert inst.api_url("/api/cron/logs") == "https://10.0.0.1:1234/youlilucky/api/cron/logs"
    assert inst.api_url("/webservice/rules_lite") == "https://10.0.0.1:1234/youlilucky/api/webservice/rules_lite"


def test_app_config_model():
    cfg = AppConfig.model_validate({})
    assert cfg.instances == []
    assert cfg.cleanup.enabled is False
