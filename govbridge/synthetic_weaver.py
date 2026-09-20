import hashlib,random
TEMPLATES={
 "newborn-registration":{"fields":["guardian","child","birth_event","facility"]},
 "address-change":{"fields":["person","old_address","new_address"]},
 "business-filing":{"fields":["business","owners","filing"]},
 "health-registry":{"fields":["synthetic_patient","encounters"]},
 "customs-training":{"fields":["shipment","declaration","inspection"]},
}
def fake_profile(index,region="central"):
    seed=int(hashlib.sha256(f"{region}:{index}".encode()).hexdigest()[:16],16);r=random.Random(seed)
    sid=f"SYN-{region[:2].upper()}-{index:010d}-{r.randrange(1000,9999)}"
    return {"synthetic_id":sid,"region":region,"age":r.randrange(18,80),"household_size":r.randrange(1,9),"training_only":True}
def generate(count,offset=0,region="central"):
    # Stream-friendly API: callers page generation instead of materializing millions in memory.
    count=max(1,min(int(count),10000))
    return [fake_profile(i,region) for i in range(offset,offset+count)]
def templates():return TEMPLATES
