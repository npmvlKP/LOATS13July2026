# F8-V-01 companion recipe: one unique basetemp per pytest session,
# forward slashes only (PYTEST_ADDOPTS/shlex eats backslashes), and
# set/run/cleanup in ONE invocation so the cleanup always has the path.
$ErrorActionPreference = 'Stop'
$bt = ($env:LOCALAPPDATA + '/Temp/pt-verify-' + [guid]::NewGuid().ToString('N').Substring(0, 8)).Replace('\', '/')
if ($bt.Contains('\')) { throw 'basetemp still carries a backslash - aborting' }
Write-Output "basetemp=$bt"
Set-Location 'G:/.OA/LOATS-13July2026/LOATS13July2026'
& .\loatsNEW\Scripts\python.exe -m pytest tests/test_repo_hygiene.py -q -p no:cacheprovider --basetemp=$bt
$rc = $LASTEXITCODE
Remove-Item -Recurse -Force $bt -ErrorAction SilentlyContinue
Write-Output "pytest_rc=$rc"
