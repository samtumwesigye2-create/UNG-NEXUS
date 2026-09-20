_assets={};_references={}
def publish_asset(region,key,digest):_assets.setdefault(region,{})[key]={"digest":digest,"immutable":True};return _assets[region][key]
def mount_reference(name,version,digest):_references[name]={"version":version,"digest":digest,"read_only":True};return _references[name]
def manifest(region):return {"region":region,"assets":_assets.get(region,{}),"reference_shards":_references}
