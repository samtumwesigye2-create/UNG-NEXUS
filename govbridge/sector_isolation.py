ALLOWED_CROSS_SECTOR={
 "civilian":{"identity","business","health","land"},
 "identity":{"civilian","health","business"},
 "health":{"identity","civilian"},
 "financial":{"business","identity"},
 "emergency":{"identity","civilian","critical-infrastructure"},
}
def allowed(source_sector,target_sector):
    if source_sector==target_sector:return True
    return target_sector in ALLOWED_CROSS_SECTOR.get(source_sector,set())
