# Only files named Test*.py are picked up. The release workflow calls this script rather than repeating
# the loop, so the two cannot drift apart.
#
# Almost every module shares one process. The modules in $isolated cannot: the fork's own install() and
# apply() patch the real ok_tasks handler lists and never put them back, so a module that reads those
# lists expecting upstream's own shape sees whatever ran before it. Isolating the readers is cheaper than
# making every install reversible. A new module that starts failing only in a full run, and passes on its
# own, belongs on this list.
$env:PYTHONIOENCODING = 'UTF-8'

$isolated = @('TestUpstreamManifest')

$all = Get-ChildItem -LiteralPath tests -Filter "Test*.py" | Sort-Object Name | ForEach-Object { $_.BaseName }
$shared = $all | Where-Object { $isolated -notcontains $_ }
$failed = 0

if ($shared) {
    Write-Host "Running $($shared.Count) modules in one process"
    python -u -m unittest -v @($shared | ForEach-Object { "tests.$_" })
    if ($LASTEXITCODE -ne 0) { $failed = 1 }
}

foreach ($module in $all | Where-Object { $isolated -contains $_ }) {
    Write-Host "Running tests.$module (isolated)"
    python -u -m unittest "tests.$module" -v
    if ($LASTEXITCODE -ne 0) { $failed = 1 }
}

if ($failed -ne 0) { Write-Host "FAILED"; exit 1 }
Write-Host "All tests passed"
