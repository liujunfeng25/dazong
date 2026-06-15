"""Unified data-quality rules and persistence for ZG market analytics."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime
from statistics import median
from typing import Any, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.zg_materialize import _price_to_float, make_sku_key


QUALITY_TBL = "data_quality_flags"
RAW_TBL = settings.zgncpjgw_price_table or "zgncpjgw_price_crawl"
HIGH_RATIO = 5.0
MEDIUM_RATIO = 3.0
HUMAN_STATUSES = {"confirmed_valid", "corrected", "quarantined", "resolved"}
ACTIVE_STATUSES = {"open", "quarantined"}


async def ensure_quality_table(db: AsyncSession) -> None:
    await db.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS `{QUALITY_TBL}` (
                `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
                `data_date` DATE NOT NULL,
                `sku_key` VARCHAR(640) NOT NULL,
                `district_name` VARCHAR(128) NOT NULL DEFAULT '',
                `goods_name` VARCHAR(256) NOT NULL DEFAULT '',
                `cate_id` INT NOT NULL DEFAULT 0,
                `cate_name` VARCHAR(128) NOT NULL DEFAULT '',
                `scate_name` VARCHAR(128) NOT NULL DEFAULT '',
                `anomaly_type` VARCHAR(64) NOT NULL,
                `severity` VARCHAR(16) NOT NULL DEFAULT 'medium',
                `reason` VARCHAR(1000) NOT NULL DEFAULT '',
                `evidence_json` JSON NULL,
                `status` VARCHAR(24) NOT NULL DEFAULT 'open',
                `corrected_price` DECIMAL(12,2) NULL,
                `review_note` VARCHAR(1000) NOT NULL DEFAULT '',
                `reviewed_by_user_id` INT NULL,
                `reviewed_at` DATETIME NULL,
                `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY `uq_quality_flag` (`data_date`, `sku_key`(255), `district_name`, `anomaly_type`),
                KEY `idx_quality_day_severity` (`data_date`, `severity`, `status`),
                KEY `idx_quality_sku_day` (`sku_key`(255), `data_date`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
    )


def _row_value(row: Any, name: str, index: int) -> Any:
    if hasattr(row, name):
        return getattr(row, name)
    return row[index]


def detect_quality_flags(rows: Iterable[Any], data_date: date) -> list[dict[str, Any]]:
    """Detect cross-province price-ratio anomalies at SKU level."""
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        goods_name = str(_row_value(row, "goods_name", 0) or "")
        if not goods_name:
            continue
        spec = str(_row_value(row, "spec", 1) or "")
        unit = str(_row_value(row, "unit", 2) or "")
        cate_id = int(_row_value(row, "cate_id", 3) or 0)
        cate_name = str(_row_value(row, "cate_name", 4) or "")
        scate_name = str(_row_value(row, "scate_name", 5) or "")
        district = str(_row_value(row, "district_name", 6) or "")
        price = _price_to_float(_row_value(row, "price", 7))
        if price is None or price <= 0:
            continue
        sku_key = make_sku_key(goods_name, spec, unit, cate_id, scate_name)
        bucket = buckets.setdefault(
            sku_key,
            {
                "goods_name": goods_name,
                "cate_id": cate_id,
                "cate_name": cate_name,
                "scate_name": scate_name,
                "prices": defaultdict(list),
                "sample_count": 0,
            },
        )
        bucket["prices"][district].append(float(price))
        bucket["sample_count"] += 1

    flags: list[dict[str, Any]] = []
    for sku_key, bucket in buckets.items():
        province_prices = {
            province: float(median(values))
            for province, values in bucket["prices"].items()
            if province and values
        }
        if len(province_prices) < 2:
            continue
        # 以各省中位价的中位数为基准（抗离群），逐省看偏离倍数，只标记离谱的那个省。
        cross_median = float(median(list(province_prices.values())))
        if cross_median <= 0:
            continue
        ordered = sorted(province_prices.items(), key=lambda item: item[1])
        low_province, low_price = ordered[0]
        high_province, high_price = ordered[-1]
        for province, price in province_prices.items():
            if price <= 0:
                continue
            ratio = max(price / cross_median, cross_median / price)
            if ratio <= MEDIUM_RATIO:
                continue
            severity = "high" if ratio > HIGH_RATIO else "medium"
            level_label = f"超过{HIGH_RATIO:.0f}倍高风险阈值" if severity == "high" else f"超过{MEDIUM_RATIO:.0f}倍关注阈值"
            reason = (
                f"{province}报价 {price:.2f} 与跨省中位价 {cross_median:.2f} 偏离 {ratio:.1f} 倍，{level_label}"
            )
            evidence = {
                "price_ratio": round(ratio, 3),
                "province_price": round(price, 3),
                "cross_median": round(cross_median, 3),
                "min_price": round(low_price, 3),
                "max_price": round(high_price, 3),
                "min_province": low_province,
                "max_province": high_province,
                "province_count": len(province_prices),
                "sample_count": int(bucket["sample_count"]),
            }
            flags.append(
                {
                    "data_date": data_date,
                    "sku_key": sku_key,
                    "district_name": province,
                    "goods_name": bucket["goods_name"],
                    "cate_id": bucket["cate_id"],
                    "cate_name": bucket["cate_name"],
                    "scate_name": bucket["scate_name"],
                    "anomaly_type": "cross_province_price_ratio",
                    "severity": severity,
                    "reason": reason,
                    "evidence_json": json.dumps(evidence, ensure_ascii=False),
                }
            )
    return flags


async def sync_quality_flags_for_day(
    db: AsyncSession,
    data_date: date,
    *,
    raw_rows: Optional[list[Any]] = None,
    commit: bool = False,
) -> list[dict[str, Any]]:
    await ensure_quality_table(db)
    if raw_rows is None:
        result = await db.execute(
            text(
                f"SELECT goods_name, spec, unit, cate_id, cate_name, scate_name, district_name, price "
                f"FROM `{RAW_TBL}` WHERE crawl_date = :d"
            ),
            {"d": data_date},
        )
        raw_rows = list(result.fetchall())
    flags = detect_quality_flags(raw_rows, data_date)
    detected_keys = {(item["sku_key"], item["district_name"], item["anomaly_type"]) for item in flags}
    for item in flags:
        await db.execute(
            text(
                f"""
                INSERT INTO `{QUALITY_TBL}`
                  (data_date, sku_key, district_name, goods_name, cate_id, cate_name, scate_name,
                   anomaly_type, severity, reason, evidence_json, status)
                VALUES
                  (:data_date, :sku_key, :district_name, :goods_name, :cate_id, :cate_name, :scate_name,
                   :anomaly_type, :severity, :reason, CAST(:evidence_json AS JSON), 'open')
                ON DUPLICATE KEY UPDATE
                  goods_name=VALUES(goods_name), cate_id=VALUES(cate_id), cate_name=VALUES(cate_name),
                  scate_name=VALUES(scate_name), severity=VALUES(severity), reason=VALUES(reason),
                  evidence_json=VALUES(evidence_json),
                  status=IF(status IN ('confirmed_valid','corrected','quarantined'), status, 'open')
                """
            ),
            item,
        )
    existing = await db.execute(
        text(
            f"SELECT id, sku_key, district_name, anomaly_type, status FROM `{QUALITY_TBL}` "
            "WHERE data_date=:d AND anomaly_type='cross_province_price_ratio'"
        ),
        {"d": data_date},
    )
    stale_ids = [
        int(row.id)
        for row in existing.fetchall()
        if (row.sku_key, row.district_name, row.anomaly_type) not in detected_keys and row.status not in HUMAN_STATUSES
    ]
    if stale_ids:
        await db.execute(
            text(f"UPDATE `{QUALITY_TBL}` SET status='resolved' WHERE id IN ({','.join(str(x) for x in stale_ids)})")
        )
    if commit:
        await db.commit()
    return flags


async def quality_map_for_days(
    db: AsyncSession,
    days: Iterable[date],
    *,
    sync_missing: bool = True,
) -> dict[tuple[date, str], dict[str, Any]]:
    uniq_days = sorted(set(days))
    if not uniq_days:
        return {}
    await ensure_quality_table(db)
    if sync_missing:
        for day in uniq_days:
            await sync_quality_flags_for_day(db, day)
    params = {f"d{i}": day for i, day in enumerate(uniq_days)}
    placeholders = ", ".join(f":d{i}" for i in range(len(uniq_days)))
    result = await db.execute(
        text(
            f"SELECT data_date, sku_key, district_name, severity, reason, status, corrected_price "
            f"FROM `{QUALITY_TBL}` WHERE data_date IN ({placeholders})"
        ),
        params,
    )
    out: dict[tuple[date, str, str], dict[str, Any]] = {}
    rank = {"none": 0, "medium": 1, "high": 2}
    for row in result.fetchall():
        if row.status in {"confirmed_valid", "resolved"}:
            continue
        # 省级键：(日期, sku_key, 省)；同时回填一个 sku 级聚合键(省="")便于全国/看板按 SKU 汇总
        for key in ((row.data_date, row.sku_key, row.district_name or ""), (row.data_date, row.sku_key, "")):
            item = out.setdefault(
                key,
                {"quality_level": "none", "quality_reasons": [], "statuses": [], "corrected_price": None},
            )
            level = "high" if row.status == "quarantined" else (row.severity or "medium")
            if rank.get(level, 0) > rank.get(item["quality_level"], 0):
                item["quality_level"] = level
            if row.reason and row.reason not in item["quality_reasons"]:
                item["quality_reasons"].append(row.reason)
            item["statuses"].append(row.status)
            if row.status == "corrected" and row.corrected_price is not None:
                item["corrected_price"] = float(row.corrected_price)
    return out


def should_exclude_quality(meta: Optional[dict[str, Any]], policy: str) -> bool:
    if not meta:
        return False
    normalized = normalize_quality_policy(policy)
    if normalized == "all":
        return False
    statuses = set(meta.get("statuses") or [])
    if statuses & {"confirmed_valid", "corrected"}:
        return False
    if "quarantined" in statuses:
        return True
    if normalized == "strict" and meta.get("quality_level") == "high":
        return True
    return False


def normalize_quality_policy(policy: Any) -> str:
    value = str(policy or "strict").strip().lower()
    return value if value in {"strict", "warn", "all"} else "strict"


def quality_weight(meta: Optional[dict[str, Any]]) -> float:
    if not meta:
        return 1.0
    return 0.5 if meta.get("quality_level") == "medium" else 1.0


def parse_evidence(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}


def now_naive() -> datetime:
    return datetime.now().replace(tzinfo=None)


def format_forecast_sample_hint(
    *,
    eligible_days: int,
    raw_days: int,
    scope_label: str = "当前口径",
    flag_status: Optional[str] = None,
    flag_severity: Optional[str] = None,
) -> str:
    """生成预测样本为 0 时的用户可读说明，区分脏数据排除与真实缺数。"""
    if eligible_days > 0:
        return ""
    status_txt = {"open": "待处理", "quarantined": "已隔离"}.get(str(flag_status or ""), "")
    flagged = flag_status in {"open", "quarantined"}
    if flagged and raw_days > 0:
        severity_note = "（高风险）" if flag_severity == "high" else ""
        return (
            f"该 SKU 在「疑似脏数据」名单中{severity_note}{('·' + status_txt) if status_txt else ''}，"
            "因源站跨省价格倍数异常，AI 训练样本已按质量规则排除，故显示 0 天。"
            "左侧热力地图展示的是源站原始报价，不代表可用于预测的数据。"
            "请先在脏数据明细中「修正」核验或「隔离」后再更新预测。"
        )
    if flagged:
        return (
            f"该 SKU 在「疑似脏数据」名单中{('·' + status_txt) if status_txt else ''}，"
            "当前口径下暂无可用于训练的历史样本。请先处置脏数据后再更新预测。"
        )
    if raw_days > 0:
        return (
            f"{scope_label}下有 {raw_days} 天原始报价，但经质量规则筛选后无可用训练样本。"
            "请检查数据质量或切换口径后再试。"
        )
    if "省" in scope_label or "口径" in scope_label:
        return (
            f"{scope_label}下暂无该 SKU 的历史报价记录，无法训练省口径预测。"
            "可切换「全国」口径，或通过补抓补齐历史数据。"
        )
    return "当前口径下暂无可用历史样本，请补抓数据或切换口径后再试。"


async def latest_active_quality_flag(db: AsyncSession, sku_key: str) -> Optional[dict[str, Any]]:
    await ensure_quality_table(db)
    result = await db.execute(
        text(
            f"""
            SELECT status, severity, reason, data_date
            FROM `{QUALITY_TBL}`
            WHERE sku_key = :sk AND status IN ('open', 'quarantined')
            ORDER BY data_date DESC
            LIMIT 1
            """
        ),
        {"sk": sku_key},
    )
    row = result.fetchone()
    if not row:
        return None
    return {
        "status": str(row.status or ""),
        "severity": str(row.severity or ""),
        "reason": str(row.reason or ""),
        "data_date": row.data_date,
    }


async def build_forecast_sample_hint(
    db: AsyncSession,
    sku_key: str,
    *,
    eligible_days: int,
    raw_days: int,
    scope_label: str = "当前口径",
) -> str:
    flag = await latest_active_quality_flag(db, sku_key)
    return format_forecast_sample_hint(
        eligible_days=eligible_days,
        raw_days=raw_days,
        scope_label=scope_label,
        flag_status=flag.get("status") if flag else None,
        flag_severity=flag.get("severity") if flag else None,
    )
