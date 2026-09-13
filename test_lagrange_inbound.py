import os

os.environ.setdefault('LAGRANGE_INBOUND_SECRET', 'test-inbound-secret')
os.environ.setdefault('LAGRANGE_INBOUND_KEY_ID', 'primary')

from fastapi.testclient import TestClient

from app import app


def test_lagrange_capabilities_are_exposed():
    response = TestClient(app).get('/v1/lagrange/capabilities')
    assert response.status_code == 200
    data = response.json()
    assert data['system'] == 'UNG-NEXUS'
    assert 'lagrange_inbound' in data['capabilities']
    assert 'orchestration' in data['capabilities']


def test_unsigned_lagrange_inbound_is_rejected():
    response = TestClient(app).post(
        '/v1/lagrange/inbound',
        json={
            'message_id': 'probe-1',
            'source_system': 'UNG-LAGRANGE',
            'target_system': 'UNG-NEXUS',
            'message_type': 'acceptance.probe',
            'payload': {'probe': True},
            'schema_version': '1.0',
        },
    )
    assert response.status_code == 401
