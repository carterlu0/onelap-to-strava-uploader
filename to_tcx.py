"""
FIT → TCX 转换器 (含心率/功率/踏频/速度/海拔)
TCX 对功率的原生支持最好，Strava 完美兼容
"""
import sys, os
from datetime import datetime as dt

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from fit_tool.fit_file import FitFile
from fit_fixer import gcj02_to_wgs84


def fit_to_tcx(filepath: str, fix_gcj02: bool = True) -> str:
    fit = FitFile.from_file(filepath)
    records = []
    start_time = None

    for rec in fit.records:
        if rec.is_definition:
            continue
        msg = rec.message
        if msg is None or msg.global_id != 20:
            continue

        lat = msg.position_lat
        lng = msg.position_long
        if not (lat and lng and lat != 0 and lng != 0):
            continue

        if fix_gcj02:
            lng, lat = gcj02_to_wgs84(lng, lat)

        ts = msg.timestamp
        ts_str = ts.isoformat() if hasattr(ts, 'isoformat') else \
            dt.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else ""

        ele = getattr(msg, 'altitude', None) or getattr(msg, 'enhanced_altitude', None)
        hr = int(getattr(msg, 'heart_rate', 0) or 0)
        cad = int(getattr(msg, 'cadence', 0) or 0)
        pwr = int(getattr(msg, 'power', 0) or 0)
        spd = getattr(msg, 'speed', None)
        dist = getattr(msg, 'distance', None)

        records.append({'ts': ts_str, 'lat': lat, 'lng': lng, 'ele': ele,
                        'hr': hr, 'cad': cad, 'pwr': pwr, 'spd': spd, 'dist': dist})
        if start_time is None:
            start_time = ts_str

    if not records:
        return None

    return build_tcx(records)


def build_tcx(records) -> str:
    total_sec = 3600
    dist_m = records[-1].get('dist', 0) or 0

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"',
        '  xmlns:ns2="http://www.garmin.com/xmlschemas/ActivityExtension/v2">',
        '  <Activities>',
        '    <Activity Sport="Biking">',
        f'      <Id>{records[0]["ts"]}</Id>',
        f'      <Lap StartTime="{records[0]["ts"]}">',
        f'        <TotalTimeSeconds>{total_sec}</TotalTimeSeconds>',
        f'        <DistanceMeters>{dist_m:.1f}</DistanceMeters>',
        '        <Intensity>Active</Intensity>',
        '        <TriggerMethod>Manual</TriggerMethod>',
        '        <Track>',
    ]

    for r in records:
        lines.append('          <Trackpoint>')
        lines.append(f'            <Time>{r["ts"]}</Time>')
        lines.append('            <Position>')
        lines.append(f'              <LatitudeDegrees>{r["lat"]:.8f}</LatitudeDegrees>')
        lines.append(f'              <LongitudeDegrees>{r["lng"]:.8f}</LongitudeDegrees>')
        lines.append('            </Position>')

        if r.get('ele') is not None:
            lines.append(f'            <AltitudeMeters>{r["ele"]:.1f}</AltitudeMeters>')
        if r.get('dist') is not None:
            lines.append(f'            <DistanceMeters>{r["dist"]:.1f}</DistanceMeters>')

        # 心率 / 踏频 → TCX 原生元素
        if r.get('hr'):
            lines.append(f'            <HeartRateBpm><Value>{r["hr"]}</Value></HeartRateBpm>')
        if r.get('cad'):
            lines.append(f'            <Cadence>{r["cad"]}</Cadence>')

        # 功率 → TCX ns2 扩展
        if r.get('pwr'):
            lines.append(f'            <Extensions><ns2:TPX><ns2:Watts>{r["pwr"]}</ns2:Watts></ns2:TPX></Extensions>')

        lines.append('          </Trackpoint>')

    lines.append('        </Track>')
    lines.append('      </Lap>')
    lines.append('    </Activity>')
    lines.append('  </Activities>')
    lines.append('</TrainingCenterDatabase>')

    return '\n'.join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python to_tcx.py <fit_file> [--no-fix]")
        sys.exit(1)
    fp = sys.argv[1]
    fix = "--no-fix" not in sys.argv
    tcx = fit_to_tcx(fp, fix_gcj02=fix)
    if tcx:
        out = os.path.splitext(fp)[0] + ("_fixed.tcx" if fix else ".tcx")
        with open(out, 'w', encoding='utf-8') as f:
            f.write(tcx)
        print(f"TCX saved: {out} ({len(tcx)} bytes)")
    else:
        print("No records found in FIT file")
