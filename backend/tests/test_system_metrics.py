"""System temperature telemetry reports real hardware readings or explicit unavailability."""
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

from app.api.v1 import system


def test_unavailable_sensors_return_none_instead_of_simulated_values(monkeypatch):
    monkeypatch.delattr(system.psutil, 'sensors_temperatures', raising=False)
    monkeypatch.setattr(system.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(subprocess, 'check_output', Mock(side_effect=OSError('wmic unavailable')))
    assert system._get_cpu_temp() is None


def test_psutil_sensor_reading_is_preferred_and_rounded(monkeypatch):
    temps = {'coretemp': [SimpleNamespace(current=45.678)]}
    monkeypatch.setattr(
        system.psutil, 'sensors_temperatures', Mock(return_value=temps), raising=False,
    )
    monkeypatch.setattr(system.platform, 'system', lambda: 'Linux')
    assert system._get_cpu_temp() == 45.7


def test_mac_helper_fallback_is_parsed_when_psutil_unavailable(monkeypatch):
    monkeypatch.delattr(system.psutil, 'sensors_temperatures', raising=False)
    monkeypatch.setattr(system.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(subprocess, 'check_output', Mock(return_value='45.2°C\n'))
    assert system._get_cpu_temp() == 45.2


def test_windows_cim_temperature_is_read_via_powershell(monkeypatch):
    monkeypatch.delattr(system.psutil, 'sensors_temperatures', raising=False)
    monkeypatch.setattr(system.platform, 'system', lambda: 'Windows')
    check_output = Mock(return_value='27.9\n')
    monkeypatch.setattr(subprocess, 'check_output', check_output)
    assert system._get_cpu_temp() == 27.9
    assert check_output.call_args.args[0][0] == 'powershell'


def test_windows_cim_empty_thermal_zone_reports_unavailable(monkeypatch):
    monkeypatch.delattr(system.psutil, 'sensors_temperatures', raising=False)
    monkeypatch.setattr(system.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(subprocess, 'check_output', Mock(return_value='\n'))
    assert system._get_cpu_temp() is None
