import csv, io, json

def fixed_width_to_json(text: str, fields: list[dict]) -> list[dict]:
    rows=[]
    for line in text.splitlines():
        if not line.strip(): continue
        row={}
        for f in fields:
            start=int(f["start"]); end=int(f["end"])
            row[f["name"]]=line[start:end].rstrip()
        rows.append(row)
    return rows

def csv_to_json(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))

def translate(payload: dict) -> dict:
    fmt=str(payload.get("_format","json")).lower()
    if fmt=="json": return {k:v for k,v in payload.items() if k!="_format"}
    if fmt=="fixed-width":
        return {"records":fixed_width_to_json(str(payload.get("data","")),payload.get("fields") or []),
                "_source_metadata":payload.get("_metadata") or {}}
    if fmt=="csv":
        return {"records":csv_to_json(str(payload.get("data",""))),
                "_source_metadata":payload.get("_metadata") or {}}
    raise ValueError("unsupported_schema_format")
