"""
FIT 文件 GCJ-02 → WGS-84 坐标修正工具
=====================================
功能:
1. 自动检测 FIT 文件中的坐标是 GCJ-02 还是 WGS-84
2. 如果是 GCJ-02，自动转换为 WGS-84
3. 修正后直接写回原文件（或生成新文件）

原理:
- GCJ-02 (火星坐标系): 中国国测局加密，偏移 100-700m
- WGS-84: GPS 原始坐标，Strava / Google Maps 等国际平台使用
- 检测算法: 利用 GCJ-02 在国内范围(中国)有明显偏移的特性，
  检查记录点落在中国境内但偏移方向一致时判定为 GCJ-02
"""
import os
import math
import struct
import logging
from typing import Tuple, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GCJ-02 ←→ WGS-84 坐标转换核心算法
# 来源: 开源算法，精度 ~1-2 米（中国境内）
# ---------------------------------------------------------------------------

PI = math.pi
A = 6378245.0          # 长半轴
EE = 0.00669342162296594323  # 偏心率平方


def _is_out_of_china(lng: float, lat: float) -> bool:
    """判断坐标是否在中国境外（GCJ-02 仅对中国境内有效）"""
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)


def _transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * PI) + 40.0 * math.sin(y / 3.0 * PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * PI) + 320.0 * math.sin(y * PI / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lng(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * PI) + 40.0 * math.sin(x / 3.0 * PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * PI) + 300.0 * math.sin(x / 30.0 * PI)) * 2.0 / 3.0
    return ret


def _wgs84_to_gcj02(lng: float, lat: float) -> Tuple[float, float]:
    """WGS-84 → GCJ-02（仅用于验证，实际不需要）"""
    if _is_out_of_china(lng, lat):
        return lng, lat
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * PI
    magic = math.sin(radlat)
    magic = 1 - EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((A * (1 - EE)) / (magic * sqrtmagic) * PI)
    dlng = (dlng * 180.0) / (A / sqrtmagic * math.cos(radlat) * PI)
    return lng + dlng, lat + dlat


def gcj02_to_wgs84(lng: float, lat: float) -> Tuple[float, float]:
    """
    GCJ-02 → WGS-84 高精度迭代转换
    精度: ~1 米（中国境内）
    """
    if _is_out_of_china(lng, lat):
        return lng, lat
    wgs_lng, wgs_lat = lng, lat
    for _ in range(5):  # 5 次迭代足够收敛
        gcj_lng, gcj_lat = _wgs84_to_gcj02(wgs_lng, wgs_lat)
        delta_lng = gcj_lng - lng
        delta_lat = gcj_lat - lat
        if abs(delta_lng) < 1e-7 and abs(delta_lat) < 1e-7:
            break
        wgs_lng -= delta_lng
        wgs_lat -= delta_lat
    return wgs_lng, wgs_lat


def offset_distance(lng: float, lat: float) -> float:
    """计算 GCJ-02 相对 WGS-84 的偏移距离（米）"""
    wgs_lng, wgs_lat = gcj02_to_wgs84(lng, lat)
    # 简化的米制距离计算
    dlat = (wgs_lat - lat) * 111320.0
    dlng = (wgs_lng - lng) * 111320.0 * math.cos(lat * PI / 180.0)
    return math.sqrt(dlat * dlat + dlng * dlng)


# ---------------------------------------------------------------------------
# FIT 文件二进制解析（最小实现，不依赖 fitparse / fit-tool）
# ---------------------------------------------------------------------------

# FIT 文件头结构: 14 字节
#   [0]    1B  头部大小 (通常 12 或 14)
#   [1]    1B  协议版本
#   [2:4]  2B  profile 版本 (LE)
#   [4:8]  4B  数据大小 (LE)
#   [8:12] 4B  数据 signature: b".FIT"
#   [12:14] 2B CRC (仅头部大小为 14 时存在)

# 记录消息头 (1 byte):
#   bit 7:   是否 compressed timestamp
#   bit 6:   消息类型 (0=data, 1=definition)
#   bit 5:   本地消息类型 (0-15)
#   bit 4:   保留
#   bit 3-0: 本地消息类型

# Definition 消息字段:
#   [0]: 保留
#   [1]: 架构 (0=LE, 1=BE)
#   [2:3]: 全局消息号 (LE)
#   [4]: 字段数量
#   后面: 每个字段 3 字节 (定义号, 大小, 基础类型)

# Record 消息的坐标字段:
#   global_msg_num = 20 (record)
#   字段 0: position_lat  (semicircles, 4 字节)
#   字段 1: position_long (semicircles, 4 字节)

SEMICIRCLE_TO_DEG = 180.0 / (2 ** 31)


def _semicircle_to_deg(val: int) -> float:
    """semicircles → 度数"""
    return val * SEMICIRCLE_TO_DEG


def _deg_to_semicircle(deg: float) -> int:
    """度数 → semcircles"""
    return int(round(deg / SEMICIRCLE_TO_DEG))


def _read_le(data: bytes, offset: int, size: int) -> int:
    """读取小端整数"""
    return int.from_bytes(data[offset:offset + size], 'little')


def _write_le(data: bytearray, offset: int, value: int, size: int):
    """写入小端整数"""
    data[offset:offset + size] = value.to_bytes(size, 'little')


class FitParser:
    """
    轻量 FIT 文件解析器
    提取所有 record 消息中的坐标点，并支持原地修改坐标
    """

    def __init__(self, filepath: str):
        self.filepath = filepath
        with open(filepath, "rb") as f:
            self.raw = bytearray(f.read())
        self.header_size = self.raw[0]
        self.data_size = _read_le(self.raw, 4, 4)
        self._definitions: dict[int, tuple] = {}  # local_num → (global_num, fields, rec_size)
        self.coordinate_records: list[dict] = []  # 所有坐标记录

    def parse_records(self) -> List[dict]:
        """
        遍历所有 record 消息，提取坐标点
        正确处理 FIT 协议的 definition/record 消息结构
        """
        records = []
        offset = self.header_size
        end = self.header_size + self.data_size
        if end > len(self.raw):
            end = len(self.raw)

        while offset < end - 1:
            header = self.raw[offset]
            is_definition = (header >> 6) & 1
            local_num = header & 0x0F
            offset += 1

            if is_definition:
                # 解析 definition，记录字段布局
                global_num = _read_le(self.raw, offset + 2, 2)
                num_fields = self.raw[offset + 4]
                offset += 5

                fields = {}
                field_offset = 0
                for i in range(num_fields):
                    fd = self.raw[offset + i * 3]      # field definition number
                    fs = self.raw[offset + i * 3 + 1]  # field size
                    fields[fd] = (fs, field_offset)
                    field_offset += fs

                self._definitions[local_num] = (global_num, fields, field_offset)
                offset += num_fields * 3

            else:
                # 解析 record，使用已知的 definition 布局
                if local_num in self._definitions:
                    gn, fields, rec_size = self._definitions[local_num]

                    # global_msg_num == 20 是 record 消息
                    if gn == 20 and 0 in fields and 1 in fields:
                        # 检查是否有 timestamp 前缀
                        has_timestamp = (header >> 5) & 1
                        rec_offset = offset + (4 if has_timestamp else 0)

                        raw_lat = _read_le(self.raw, rec_offset + fields[0][1], 4)
                        raw_lng = _read_le(self.raw, rec_offset + fields[1][1], 4)
                        lat = _semicircle_to_deg(raw_lat)
                        lng = _semicircle_to_deg(raw_lng)

                        if lat != 0 or lng != 0:
                            records.append({
                                "offset": rec_offset + fields[0][1],  # lat 所在字节偏移
                                "lng_offset": rec_offset + fields[1][1],  # lng 所在字节偏移
                                "lat": lat,
                                "lng": lng,
                                "local_num": local_num,
                            })

                    offset += rec_size
                else:
                    # 未知 definition，无法解析，跳过
                    break

        self.coordinate_records = records
        return records

    def rewrite_coordinates(self, records: List[dict],
                             converter) -> int:
        """
        原地修改坐标
        converter: callable(lng, lat) -> (new_lng, new_lat)
        返回修改的点数
        """
        count = 0
        for rec in records:
            new_lng, new_lat = converter(rec["lng"], rec["lat"])
            if new_lng != rec["lng"] or new_lat != rec["lat"]:
                # 写回 semcircles
                _write_le(self.raw, rec["offset"],
                          _deg_to_semicircle(new_lat), 4)
                _write_le(self.raw, rec["lng_offset"],
                          _deg_to_semicircle(new_lng), 4)
                count += 1
        return count

    def save(self, filepath: str = None):
        """保存修改后的文件，并重新计算 CRC"""
        target = filepath or self.filepath
        header_size = self.raw[0]
        data_size = _read_le(self.raw, 4, 4)
        data_end = header_size + data_size
        
        # 重新计算数据区 CRC
        from binascii import crc_hqx
        crc = 0
        for i in range(header_size, data_end):
            crc = crc_hqx(bytes([self.raw[i]]), crc)
        _write_le(self.raw, data_end, crc, 2)
        
        # 重新计算头部 CRC
        crc = 0
        for i in range(0, header_size - 2):
            crc = crc_hqx(bytes([self.raw[i]]), crc)
        _write_le(self.raw, header_size - 2, crc, 2)
        
        with open(target, "wb") as f:
            f.write(self.raw)


# ---------------------------------------------------------------------------
# GCJ-02 / WGS-84 自动检测（往返验证法）
# ---------------------------------------------------------------------------

def _roundtrip_error(lng: float, lat: float) -> float:
    """
    往返误差: 对坐标做 gcj02→wgs84→gcj02 往返，看与原始点距离。
    
    原理:
    - 如果原始是 GCJ-02 → 往返误差 ~0m（变换可逆）
    - 如果原始是 WGS-84 → 往返误差 ~485m（变换方向反了，GCJ偏移无法抵消）
    """
    wgs = gcj02_to_wgs84(lng, lat)
    back = _wgs84_to_gcj02(wgs[0], wgs[1])
    dlat = (back[1] - lat) * 111320.0
    dlng = (back[0] - lng) * 111320.0 * math.cos(lat * PI / 180.0)
    return math.sqrt(dlat * dlat + dlng * dlng)


def detect_coordinate_system(points: List[Tuple[float, float]],
                              sample_size: int = 100) -> dict:
    """
    检测坐标系：单向偏移 + 修正前后对比。
    
    对每个采样点计算 gcj02_to_wgs84, 对比修正前后的距离:
    - 偏移 > 50m  → GCJ-02 (需要修正)
    - 偏移 < 5m   → WGS-84 (已经正确，不要动)
    """
    if not points:
        return {"system": "wgs84", "confidence": 1.0,
                "avg_offset_m": 0, "samples_checked": 0}

    samples = points[:sample_size] if len(points) > sample_size else points
    
    offsets = []
    in_china = 0
    for lng, lat in samples:
        if _is_out_of_china(lng, lat):
            continue
        in_china += 1
        # 计算单向偏移
        wgs_lng, wgs_lat = gcj02_to_wgs84(lng, lat)
        dlat = (wgs_lat - lat) * 111320.0
        dlng = (wgs_lng - lng) * 111320.0 * math.cos(lat * PI / 180.0)
        dist = math.sqrt(dlat * dlat + dlng * dlng)
        offsets.append(dist)
    
    if in_china == 0:
        return {"system": "wgs84", "confidence": 1.0,
                "avg_offset_m": 0, "samples_checked": len(samples)}
    
    avg_offset = sum(offsets) / len(offsets)
    
    # 关键阈值判断
    if avg_offset > 50:
        return {"system": "gcj02", "confidence": min(1.0, avg_offset / 200),
                "avg_offset_m": avg_offset, "samples_checked": len(samples)}
    elif avg_offset < 5:
        # 偏移极小 → 已是 WGS-84 或已在境外，不修正
        return {"system": "wgs84", "confidence": 0.99,
                "avg_offset_m": avg_offset, "samples_checked": len(samples)}
    else:
        # 灰色地带 (5-50m): 保守不修正
        return {"system": "wgs84", "confidence": 0.7,
                "avg_offset_m": avg_offset, "samples_checked": len(samples)}


# ---------------------------------------------------------------------------
# 主入口：修正 FIT 文件
# ---------------------------------------------------------------------------

def fix_fit_file(filepath: str, force: bool = False,
                  dry_run: bool = False) -> dict:
    """
    修正 FIT 文件中的 GCJ-02 坐标 → WGS-84

    返回:
        {
            "fixed": bool,                # 是否实际做了修正
            "system": str,       # "gcj02" | "wgs84"
            "confidence": float,
            "points_total": int,
            "points_fixed": int,
            "avg_offset_m": float,
            "filepath": str,
        }
    """
    logger.info(f"分析 FIT 文件: {os.path.basename(filepath)}")

    # Step 1: 解析坐标点
    parser = FitParser(filepath)
    records = parser.parse_records()

    if not records:
        logger.info("  未发现坐标记录，跳过修正")
        return {"fixed": False, "system": "unknown",
                "confidence": 1.0, "points_total": 0,
                "points_fixed": 0, "avg_offset_m": 0,
                "filepath": filepath}

    # Step 2: 抽样检测坐标系
    sample_points = [(r["lng"], r["lat"]) for r in records]
    detection = detect_coordinate_system(sample_points)
    logger.info(f"  检测结果: {detection['system']} "
                f"(置信度: {detection['confidence']:.1%}, "
                f"平均偏移: {detection['avg_offset_m']:.1f}m)")

    # Step 3: 如果不是 GCJ-02 且非强制，跳过
    if detection["system"] != "gcj02" and not force:
        logger.info(f"  坐标系统为 {detection['system']}，无需修正")
        return {**detection, "fixed": False,
                "points_total": len(records), "points_fixed": 0,
                "filepath": filepath}

    if dry_run:
        logger.info(f"  [预览] 将修正 {len(records)} 个坐标点")
        return {**detection, "fixed": False,
                "points_total": len(records), "points_fixed": 0,
                "filepath": filepath}

    # Step 4: 安全网 — 修正前抽样对比偏移量，太小则跳过
    if not force:
        sample = records[:min(100, len(records))]
        actual_offsets = []
        for r in sample:
            wgs_lng, wgs_lat = gcj02_to_wgs84(r["lng"], r["lat"])
            dlat = (wgs_lat - r["lat"]) * 111320.0
            dlng = (wgs_lng - r["lng"]) * 111320.0 * math.cos(r["lat"] * PI / 180.0)
            actual_offsets.append(math.sqrt(dlat * dlat + dlng * dlng))
        avg_actual = sum(actual_offsets) / len(actual_offsets)
        if avg_actual < 10:
            logger.info(f"  安全网: 实际修正偏移仅 {avg_actual:.1f}m (< 10m)，跳过修正")
            return {**detection, "fixed": False,
                    "points_total": len(records), "points_fixed": 0,
                    "filepath": filepath, "avg_offset_m": avg_actual}

    # Step 5: 执行修正
    count = parser.rewrite_coordinates(records, gcj02_to_wgs84)
    parser.save()

    logger.info(f"  ✅ 已修正 {count}/{len(records)} 个坐标点")
    return {**detection, "fixed": True,
            "points_total": len(records), "points_fixed": count,
            "filepath": filepath}


# ---------------------------------------------------------------------------
# 命令行测试
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(sys.argv) < 2:
        print("用法: python fit_fixer.py <fit文件路径> [--force] [--dry-run]")
        sys.exit(1)

    filepath = sys.argv[1]
    force = "--force" in sys.argv
    dry_run = "--dry-run" in sys.argv

    result = fix_fit_file(filepath, force=force, dry_run=dry_run)
    print()
    print("=" * 50)
    print(f"文件: {result['filepath']}")
    print(f"检测坐标系: {result['system']}")
    print(f"置信度: {result['confidence']:.1%}")
    print(f"平均偏移: {result['avg_offset_m']:.1f} 米")
    print(f"坐标点总数: {result['points_total']}")
    if result['fixed']:
        print(f"修正点数: {result['points_fixed']}")
        print("✅ 已修正 GCJ-02 → WGS-84")
    else:
        print("⏭️ 无需修正")
