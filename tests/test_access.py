"""访问日志解析 / geoip / access 数据层测试。"""
import json

import pytest

from app.access_parser import parse_access_row, parse_extinfo, ua_detail
from app.db import Database
from app.geoip import geo_short, province

UA_MOBILE = "Mozilla/5.0 (Linux; Android 11; V2068A) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.200 Mobile Safari/537.36 VivoBrowser/30.3.0.0"
UA_PC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 13.6; rv:132.0) Gecko/20100101 Firefox/132.0"


def _access_rec(ip="198.51.100.7", host="omo.example.com", url="/favicon.ico", method="GET", ua=UA_PC):
    return {
        "LogContent": json.dumps({
            "ExtInfo": {"ClientIP": ip, "Host": host, "Method": method, "URL": url, "UserAgent": ua},
            "level": "info", "msg": "fileServer",
        }),
        "LogTime": "2026/08/16 03:00:00", "ShowTime": True,
    }


def test_parse_extinfo():
    ext = parse_extinfo(_access_rec()["LogContent"])
    assert ext["ClientIP"] == "198.51.100.7"
    assert ext["URL"] == "/favicon.ico"
    assert parse_extinfo("not json") is None
    assert parse_extinfo(json.dumps({"no": "extinfo"})) is None


def test_parse_access_row_mobile():
    row = parse_access_row("inst", _access_rec(ua=UA_MOBILE), rule_key="rk", sub_key="sk")
    assert row["client_ip"] == "198.51.100.7"
    assert row["method"] == "GET"
    assert row["path"] == "/favicon.ico"
    assert row["browser"] == "VivoBrowser"
    assert row["os"] == "Android"
    assert row["device_type"] == "mobile"


def test_parse_access_row_pc():
    row = parse_access_row("inst", _access_rec(ua=UA_PC))
    assert row["device_type"] == "desktop"
    assert row["browser"] == "Firefox"


def test_parse_access_row_bot():
    rec = _access_rec(ua="Googlebot/2.1 (+http://www.google.com/bot.html)")
    row = parse_access_row("inst", rec)
    assert row["device_type"] == "bot"


def test_parse_access_row_non_web():
    rec = {"LogContent": "plain text log", "LogTime": "2026/08/16 03:00:00"}
    assert parse_access_row("inst", rec) is None


def test_parse_access_row_empty_ua():
    """UA 为空/缺失不应崩溃（曾导致 _classify_device 对 None 访问 is_bot）。"""
    rec = _access_rec(ua="")
    row = parse_access_row("inst", rec)
    assert row is not None
    assert row["device_type"] == "unknown"
    rec2 = {"LogContent": json.dumps({
        "ExtInfo": {"ClientIP": "1.2.3.4", "Host": "h", "Method": "GET", "URL": "/", "UserAgent": ""},
        "level": "info", "msg": "x",
    }), "LogTime": "2026/08/16 03:00:00"}
    row2 = parse_access_row("inst", rec2)
    assert row2["device_type"] == "unknown"


def test_geoip_private():
    assert province("127.0.0.1") == "内网/保留"
    assert province("192.168.1.1") == "内网/保留"


def test_geoip_public():
    r = province("198.51.100.7")
    assert isinstance(r, str) and r


def test_geoip_short_private():
    assert geo_short("127.0.0.1") == "内网/保留"


def test_geoip_short_public():
    r = geo_short("198.51.100.7")
    assert isinstance(r, str) and r


def test_ua_detail():
    d = ua_detail(UA_MOBILE)
    assert d["browser"] == "VivoBrowser"
    assert d["browser_version"] == "30.3.0"
    assert d["os"] == "Android"
    assert d["os_version"] == "11"
    assert d["device_type"] == "mobile"
    d2 = ua_detail("")
    assert d2["browser"] == ""


@pytest.fixture
async def db(tmp_path):
    d = Database(str(tmp_path / "t.db"))
    await d.connect()
    yield d
    await d.close()


async def test_insert_access_dedup_and_query(db):
    rows = [parse_access_row("inst", _access_rec(), sub_key="sk", rule_key="rk"),
            parse_access_row("inst", _access_rec(ip="2.2.2.2"), sub_key="sk", rule_key="rk")]
    assert await db.insert_access_logs(rows) == 2
    assert await db.insert_access_logs(rows) == 0  # 去重
    st = await db.access_stats(instance="inst")
    assert st["total"] == 2
    assert st["unique_ips"] == 2
    q = await db.query_access_logs(instance="inst", sub_key="sk")
    assert q["total"] == 2
    assert q["items"][0]["client_ip"] in ("198.51.100.7", "2.2.2.2")


async def test_access_stats_groups(db):
    rows = [
        parse_access_row("inst", _access_rec(ip="1.1.1.1", url="/a"), sub_key="s1"),
        parse_access_row("inst", _access_rec(ip="1.1.1.1", url="/b", ua=UA_MOBILE), sub_key="s1"),
        parse_access_row("inst", _access_rec(ip="2.2.2.2", url="/a"), sub_key="s2"),
    ]
    await db.insert_access_logs(rows)
    st = await db.access_stats(instance="inst")
    assert st["total"] == 3
    assert st["unique_paths"] == 2
    assert st["top_ips"][0]["k"] == "1.1.1.1"
    assert st["top_ips"][0]["count"] == 2
    assert {d["k"] for d in st["device_types"]} >= {"mobile", "desktop"}
    assert any(h["k"] == "omo.example.com" for h in st["hosts"])


async def test_service_or_filter(db):
    from tests.test_db import _row
    await db.insert_logs([
        _row(module="webservice", rule_key="rk1", sub_key="", content="rule log"),
        _row(module="webservice", rule_key="rk1", sub_key="sk1", content="sub log"),
    ])
    q = await db.query_logs(instance="inst1", service="sk1")
    assert q["total"] == 1
    assert q["items"][0]["content"] == "sub log"
    q = await db.query_logs(instance="inst1", service="rk1")
    assert q["total"] == 2


async def test_level_filter(db):
    from tests.test_db import _row
    await db.insert_logs([
        _row(module="webservice", rule_key="rk1", sub_key="", content="rule log"),
        _row(module="webservice", rule_key="rk1", sub_key="sk1", content="sub log"),
    ])
    q = await db.query_logs(instance="inst1", module="webservice", level="rule")
    assert q["total"] == 1 and q["items"][0]["sub_key"] == ""
    q = await db.query_logs(instance="inst1", module="webservice", level="sub")
    assert q["total"] == 1 and q["items"][0]["sub_key"] == "sk1"


async def test_service_counts(db):
    from tests.test_db import _row
    await db.insert_logs([
        _row(module="webservice", rule_key="rk1", rule_name="R1", sub_key="", content="rule"),
        _row(module="webservice", rule_key="rk1", rule_name="R1", sub_key="sk1", content="sub"),
    ])
    await db.insert_access_logs([
        parse_access_row("inst1", _access_rec(), rule_key="rk1", rule_name="R1", sub_key="sk1", sub_name="S1")
    ])
    counts = await db.service_counts("inst1")
    by = {(c["kind"], c["key"]): c for c in counts}
    assert by[("rule", "rk1")]["logs_count"] == 1
    assert by[("rule", "rk1")]["access_count"] == 1
    assert by[("sub", "sk1")]["logs_count"] == 1
    assert by[("sub", "sk1")]["access_count"] == 1


async def test_ip_traffic_upsert_and_aggregate(db):
    rows = [
        {"instance": "inst", "sub_key": "s1", "client_ip": "1.1.1.1",
         "last_access": 100, "connections": 1, "traffic_in": 100, "traffic_out": 900, "fetched_at": 1},
        {"instance": "inst", "sub_key": "s1", "client_ip": "1.1.1.1",
         "last_access": 200, "connections": 2, "traffic_in": 50, "traffic_out": 100, "fetched_at": 2},
        {"instance": "inst", "sub_key": "s2", "client_ip": "2.2.2.2",
         "last_access": 300, "connections": 1, "traffic_in": 10, "traffic_out": 20, "fetched_at": 3},
    ]
    assert await db.upsert_ip_traffic(rows) == 3
    m = await db.traffic_map("inst")
    assert m["1.1.1.1"]["connections"] == 2  # 同 sub 键 UPSERT 覆盖，跨子代理才累加
    assert m["1.1.1.1"]["traffic_in"] == 50
    assert m["1.1.1.1"]["last_access"] == 200
    assert m["2.2.2.2"]["traffic_out"] == 20
    s = await db.traffic_summary("inst")
    assert s["connections"] == 3
    assert s["traffic_in"] == 60
    assert s["traffic_out"] == 120
