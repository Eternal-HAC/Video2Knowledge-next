"""Exercise PowerShell smoke discovery with synthetic processes and listeners."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
$ErrorActionPreference = 'Stop'
$case = [Console]::In.ReadToEnd() | ConvertFrom-Json
. $env:V2K_SMOKE_HELPER
$script:calls = @()
function Get-CimInstance { param($ClassName, $ErrorAction) return $case.processes }
function Get-NetTCPConnection { param($State, $ErrorAction) return $case.listeners }
function Invoke-RestMethod {
    param($Uri, $TimeoutSec)
    $script:calls += $Uri
    if ($case.health_error) { throw 'synthetic unavailable' }
    return $case.health
}
$instance = [pscustomobject]@{ Id = 10; HasExited = $case.exited }
$url = Find-SmokeOwnedService -Process $instance -ExpectedVersion 'test-version'
@{ url = $url; calls = @($script:calls) } | ConvertTo-Json -Compress
'''


@pytest.mark.parametrize('mutation,expected_port', [
    ('foreign-earlier-port', 8001), ('grandchild', 8001),
    ('no-owned-listener', None), ('missing-root', None),
    ('exited', None), ('wrong-version', None), ('health-error', None),
    ('non-loopback', None), ('outside-port-range', None),
])
def test_smoke_discovery_only_contacts_owned_listener(mutation, expected_port):
    shell = shutil.which('pwsh')
    assert shell, 'PowerShell 7 is required for the Windows portable-smoke gate'
    case = {
        'processes': [{'ProcessId': 10, 'ParentProcessId': 1},
                      {'ProcessId': 11, 'ParentProcessId': 10},
                      {'ProcessId': 99, 'ParentProcessId': 1}],
        'listeners': [{'LocalPort': 8000, 'LocalAddress': '127.0.0.1', 'OwningProcess': 99},
                      {'LocalPort': 8001, 'LocalAddress': '127.0.0.1', 'OwningProcess': 11}],
        'health': {'status': 'ok', 'product': 'Video2Knowledge', 'service': 'VideoToNo',
                   'api_compat': 1, 'mode': 'portable', 'version': 'test-version'},
        'exited': False,
    }
    if mutation == 'grandchild':
        case['processes'].append({'ProcessId': 12, 'ParentProcessId': 11})
        case['listeners'][1]['OwningProcess'] = 12
    elif mutation == 'no-owned-listener':
        case['listeners'] = case['listeners'][:1]
    elif mutation == 'missing-root':
        case['processes'] = case['processes'][1:]
    elif mutation == 'exited':
        case['exited'] = True
    elif mutation == 'wrong-version':
        case['health']['version'] = 'other'
    elif mutation == 'health-error':
        case['health_error'] = True
    elif mutation == 'non-loopback':
        case['listeners'][1]['LocalAddress'] = '0.0.0.0'
    elif mutation == 'outside-port-range':
        case['listeners'][1]['LocalPort'] = 9000
    result = subprocess.run(
        [shell, '-NoProfile', '-NonInteractive', '-Command', HARNESS],
        input=json.dumps(case), text=True, capture_output=True, timeout=15,
        env={**os.environ, 'V2K_SMOKE_HELPER': str(ROOT / 'scripts/portable_smoke_common.ps1')},
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert all(':8000/' not in url for url in data['calls']), 'Never contact the foreign instance'
    assert data['url'] == (f'http://127.0.0.1:{expected_port}' if expected_port else None)
    if mutation in {'missing-root', 'exited', 'no-owned-listener', 'non-loopback', 'outside-port-range'}:
        assert data['calls'] == []


@pytest.mark.parametrize('name', ['smoke_portable_beta3.ps1', 'smoke_portable_asr.ps1'])
def test_both_smokes_use_owned_discovery(name):
    source = (ROOT / 'scripts' / name).read_text(encoding='utf-8')
    assert 'portable_smoke_common.ps1' in source
    assert 'Find-SmokeOwnedService -Process $' in source
    assert 'foreach ($port in 8000..8019)' not in source
