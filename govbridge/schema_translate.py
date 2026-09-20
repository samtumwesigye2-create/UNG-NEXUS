import csv,io,json
def fixed_width_to_json(text,fields):
    rows=[]
    for line in text.splitlines():
        if not line.strip():continue
        row={}
        for f in fields:row[f["name"]]=line[int(f["start"]):int(f["end"])].rstrip()
        rows.append(row)
    return rows
def csv_to_json(text):return list(csv.DictReader(io.StringIO(text)))
def ebcdic_to_json(hex_data,fields,codec="cp037"):
    raw=bytes.fromhex(hex_data);text=raw.decode(codec)
    return fixed_width_to_json(text,fields)
def translate(payload):
    fmt=str(payload.get("_format","json")).lower();meta=payload.get("_metadata") or {}
    if fmt=="json":return {k:v for k,v in payload.items() if k!="_format"}
    if fmt=="fixed-width":records=fixed_width_to_json(str(payload.get("data","")),payload.get("fields") or [])
    elif fmt=="csv":records=csv_to_json(str(payload.get("data","")))
    elif fmt=="ebcdic":records=ebcdic_to_json(str(payload.get("data_hex","")),payload.get("fields") or [],str(payload.get("codec","cp037")))
    else:raise ValueError("unsupported_schema_format")
    return {"records":records,"_source_metadata":meta,"_source_format":fmt}
