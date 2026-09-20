import datetime,hashlib
STATUS={"01":"ACTIVE","02":"DECEASED","03":"UNDER_REVIEW"}
def legacy_to_modern(raw):
    if len(raw)<512:raise ValueError("legacy_row_must_be_512_bytes")
    s=raw[:512].decode("cp500")
    sys_id=s[0:12].strip();nat=s[12:21].strip();sur=s[21:61].strip().title();giv=s[61:101].strip().title()
    dob=s[101:109].strip();status=STATUS.get(s[109:111].strip(),"UNDER_REVIEW");addr=s[111:211].strip()
    try:dob_iso=datetime.datetime.strptime(dob,"%Y%m%d").date().isoformat();dob_valid=True
    except ValueError:dob_iso=None;dob_valid=False
    parts=[p.strip() for p in addr.split(",") if p.strip()]
    return {"legacy_reference_id":sys_id,"national_id_hash":hashlib.sha256(nat.encode()).hexdigest(),"raw_national_id":nat,
      "family_name":sur,"given_names":giv,"date_of_birth":dob_iso,"status":status,
      "address":{"street_address":parts[0] if parts else None,"locality":parts[1] if len(parts)>1 else None},
      "metadata":{"dob_valid":dob_valid,"address_parse_confidence":"heuristic","source_encoding":"cp500"}}
def modern_to_legacy(p):
    status={"ACTIVE":"01","DECEASED":"02","UNDER_REVIEW":"03","SUSPENDED":"03"}.get(p.get("status"),"03")
    dob=(p.get("date_of_birth") or "").replace("-","")[:8]
    a=p.get("address") or {};addr=", ".join(x for x in [a.get("street_address"),a.get("locality")] if x)
    # raw national ID is required only inside the protected translation boundary.
    fields=[str(p.get("legacy_reference_id",""))[:12].ljust(12),str(p.get("raw_national_id",""))[:9].rjust(9,"0"),
      str(p.get("family_name","")).upper()[:40].ljust(40),str(p.get("given_names","")).upper()[:40].ljust(40),
      dob.ljust(8),status.ljust(2),addr[:100].ljust(100),"".ljust(301)]
    return "".join(fields)[:512].encode("cp500")
