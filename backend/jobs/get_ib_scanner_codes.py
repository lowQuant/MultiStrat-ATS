from ib_async import IB
import xml.etree.ElementTree as ET
import csv, json, argparse, sys
from pathlib import Path
import pandas as pd
import os

# Force import of backend's cloud-aware get_ac
try:
    # Add backend/ to sys.path so `core` is importable
    backend_dir = Path(__file__).resolve().parent.parent  # backend/
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    from core.arctic_manager import get_ac  # type: ignore
except Exception as e:
    raise ImportError(
        "Failed to import backend.core.arctic_manager.get_ac. Install dependencies (incl. fastapi) "
        "and run this script in the same environment as the backend. Original error: " + str(e)
    )

def gtext(node, names):
    """Return first non-empty child text among a list of tag names."""
    for n in names:
        el = node.find(n)
        if el is not None and el.text and el.text.strip():
            return el.text.strip()
    return ""

def dump_scanner_params(host="127.0.0.1", port=7497, client_id=99, outdir=Path(".")):
    ib = IB()
    ib.connect(host, port, clientId=client_id)
    xml = ib.reqScannerParameters()
    ib.disconnect()

    root = ET.fromstring(xml)

    # --- Scan types (codes + display names) ---
    scan_types = []
    for st in root.findall(".//ScanType") + root.findall(".//scan_type"):
        scan_types.append({
            "code": gtext(st, ["code", "scanCode"]),
            "display_name": gtext(st, ["displayName", "display_name"]),
        })
    # De-dup & sort
    seen = set()
    uniq_scan_types = []
    for d in scan_types:
        key = (d["code"], d["display_name"])
        if d["code"] and key not in seen:
            uniq_scan_types.append(d)
            seen.add(key)
    uniq_scan_types.sort(key=lambda x: (x["display_name"].lower(), x["code"]))

    # Exclude any scan types that contain 'bond'
    uniq_scan_types = [d for d in uniq_scan_types
                       if 'bond' not in d.get('code', '').lower()
                       and 'bond' not in d.get('display_name', '').lower()]

    # --- Filter fields (tags) ---
    filter_fields = []
    for f in root.findall(".//AbstractField"):
        filter_fields.append({
            "code": gtext(f, ["code", "tag"]),
            "display_name": gtext(f, ["displayName", "display_name"]),
            "unit": gtext(f, ["unit", "units"]),
            "data_type": gtext(f, ["type", "dataType"]),
            "min": gtext(f, ["minValue", "min"]),
            "max": gtext(f, ["maxValue", "max"]),
        })
    filter_fields = [d for d in filter_fields if d["code"]]
    # De-dup & sort
    seen = set()
    uniq_filters = []
    for d in filter_fields:
        key = (d["code"], d["display_name"], d["unit"], d["data_type"], d["min"], d["max"])
        if key not in seen:
            uniq_filters.append(d)
            seen.add(key)
    uniq_filters.sort(key=lambda x: x["code"].lower())

    # Exclude any filters that contain 'bond'
    uniq_filters = [d for d in uniq_filters
                    if 'bond' not in d.get('code', '').lower()
                    and 'bond' not in d.get('display_name', '').lower()]


    outdir.mkdir(parents=True, exist_ok=True)

    # Write JSON
    (outdir / "scanner_scan_types.json").write_text(json.dumps(uniq_scan_types, indent=2))
    (outdir / "scanner_filter_fields.json").write_text(json.dumps(uniq_filters, indent=2))

    # Write CSV
    with open(outdir / "scanner_scan_types.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["code", "display_name"])
        w.writeheader(); w.writerows(uniq_scan_types)

    with open(outdir / "scanner_filter_fields.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["code", "display_name", "unit", "data_type", "min", "max"])
        w.writeheader(); w.writerows(uniq_filters)

    print(f"Scan types:    {len(uniq_scan_types)}")
    print(f"Filter fields: {len(uniq_filters)}")
    print(f"Wrote files to {outdir.resolve()}")

    # --- Persist to ArcticDB ---
    try:
        ac = get_ac()
        # Ensure 'scanners' library exists
        libs = ac.list_libraries()
        if 'scanners' not in libs:
            ac.create_library('scanners')
        lib = ac.get_library('scanners')

        # Save scan types as 'codes'
        df_codes = pd.DataFrame(uniq_scan_types, columns=['code', 'display_name'])
        df_codes.reset_index(drop=True, inplace=True)
        lib.write('codes', df_codes)

        # Save filter fields as 'filters'
        df_filters = pd.DataFrame(uniq_filters, columns=['code', 'display_name', 'unit', 'data_type', 'min', 'max'])
        df_filters.reset_index(drop=True, inplace=True)
        lib.write('filters', df_filters)

        print("Saved scanner codes -> scanners/codes and filter codes -> scanners/filters in ArcticDB.")
    except Exception as e:
        print(f"WARNING: Failed to save to ArcticDB: {e}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Dump IBKR scanner params to CSV/JSON")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7497)
    ap.add_argument("--client-id", type=int, default=99)
    ap.add_argument("--outdir", default="ibkr_scanner_params")
    args = ap.parse_args()
    dump_scanner_params(args.host, args.port, args.client_id, Path(args.outdir))
