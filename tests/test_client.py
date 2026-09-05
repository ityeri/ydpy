"""Client table and request header builder."""

from ydpy.client import CLIENTS, DEFAULT_CLIENT_NAMES, get_default_clients, innertube_headers


def test_client_table_keys():
    assert set(CLIENTS) == {'web', 'visionos', 'tv_downgraded', 'mweb', 'android_vr'}


def test_default_client_names_chain():
    assert DEFAULT_CLIENT_NAMES == ('visionos', 'tv_downgraded', 'mweb', 'android_vr')
    # the chain does not depend on a JS runtime being present
    assert get_default_clients(js_available=True) == DEFAULT_CLIENT_NAMES
    assert get_default_clients(js_available=False) == DEFAULT_CLIENT_NAMES


def test_visionos_headers():
    headers = innertube_headers(CLIENTS['visionos'])
    assert headers['X-YouTube-Client-Name'] == '101'
    assert headers['X-YouTube-Client-Version'] == '1.02'
    assert 'Safari' in headers['User-Agent']


def test_web_headers_default_ua():
    headers = innertube_headers(CLIENTS['web'])
    assert headers['X-YouTube-Client-Name'] == '1'
    assert headers['User-Agent'].startswith('Mozilla/')
