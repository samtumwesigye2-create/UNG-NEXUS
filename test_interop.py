from interop import NexusEnvelope, Connector, ConnectorRegistry

def test_envelope_contract():
    e=NexusEnvelope('UNG-A','UNG-B','shipment.updated',{'id':'1'},priority=120,trace_id='t1')
    d=e.to_dict()
    assert d['message_id']
    assert d['schema_version']=='1.0'
    assert d['priority']==100
    assert d['trace_id']=='t1'

def test_connector_discovery():
    r=ConnectorRegistry()
    r.register(Connector('carrier-x','vendor',{'shipping','tracking'},lambda e:{'ok':True}))
    assert r.get('carrier-x') is not None
    assert [c.name for c in r.discover('tracking')]==['carrier-x']
