import json
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException

import app as nexus

router = APIRouter()


@router.get('/v1/acceptance/verified')
def verified_apollo_acceptance():
    try:
        with nexus.conn() as c:
            check = c.execute(
                "SELECT target_system,status,response_code,message_id,error,created_at "
                "FROM nexus_acceptance_checks WHERE target_system='UNG-APOLLO' "
                "ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
    except Exception as exc:
        raise HTTPException(503, f'nexus_acceptance_unavailable:{type(exc).__name__}')

    if not check:
        return {'verified': False, 'reason': 'no_acceptance_check'}

    apollo_status = None
    apollo_error = None
    if nexus.APOLLO_BASE_URL:
        try:
            req = urllib.request.Request(
                nexus.APOLLO_BASE_URL + '/v1/nexus/status',
                method='GET',
                headers={'User-Agent': 'UNG-NEXUS/0.4.4'},
            )
            with urllib.request.urlopen(req, timeout=nexus.DELIVERY_TIMEOUT) as response:
                apollo_status = json.loads(response.read().decode() or '{}')
        except urllib.error.HTTPError as exc:
            apollo_error = f'http_{exc.code}'
        except Exception as exc:
            apollo_error = type(exc).__name__

    last = (apollo_status or {}).get('last_acceptance') or {}
    same_message = bool(check.get('message_id')) and check.get('message_id') == last.get('nexus_message_id')
    verified = (
        check.get('status') == 'passed'
        and 200 <= int(check.get('response_code') or 0) < 300
        and same_message
        and last.get('status') == 'accepted'
    )

    return {
        'verified': verified,
        'route': 'UNG-NEXUS -> UNG-APOLLO',
        'message_id_match': same_message,
        'nexus': check,
        'apollo': {
            'reachable': apollo_status is not None,
            'error': apollo_error,
            'last_acceptance': last or None,
            'events': (apollo_status or {}).get('events'),
        },
    }
