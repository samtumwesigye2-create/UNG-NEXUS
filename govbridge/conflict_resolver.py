from dataclasses import dataclass
AUTHORITIES={
 "identity":["GOU-NIRA"],
 "tax":["GOU-URA"],
 "business":["GOU-URSB"],
 "statistics":["GOU-UBOS"],
}
def resolve(domain:str,records:list[dict]):
    authority=AUTHORITIES.get(domain,[])
    ranked=sorted(records,key=lambda r:(0 if r.get("source") in authority else 1,-float(r.get("updated_at",0) or 0)))
    winner=ranked[0] if ranked else None
    return {"domain":domain,"authoritative_sources":authority,"resolved":winner,"conflicts":ranked[1:]}
