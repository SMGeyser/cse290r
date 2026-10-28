param(
    [ValidateRange(0, 100)]
    [double]$MinimumCoverage = 90
)

$ErrorActionPreference = 'Stop'
$resultDirectory = Join-Path $PSScriptRoot ('TestResults/' + [guid]::NewGuid().ToString('N'))
$project = Join-Path $PSScriptRoot 'unit.csproj'
$settings = Join-Path $PSScriptRoot 'coverage.runsettings'

& dotnet test $project --collect 'XPlat Code Coverage' --settings $settings `
    --results-directory $resultDirectory --logger 'trx;LogFileName=unit-tests.trx'
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

# The TRX logger also copies attachments into its own subtree. Use the
# collector's original report directly beneath this run's result directory.
$reports = @(Get-ChildItem -LiteralPath $resultDirectory -Filter 'coverage.cobertura.xml' -Recurse |
    Where-Object { $_.Directory.Parent.FullName -eq [System.IO.Path]::GetFullPath($resultDirectory) })
if ($reports.Count -ne 1) {
    throw 'Expected exactly one fresh coverage report.'
}
[xml]$report = Get-Content -LiteralPath $reports[0].FullName -Raw
$coverage = $report.coverage
if ([int]$coverage.'lines-valid' -eq 0 -or [int]$coverage.'branches-valid' -eq 0) {
    throw 'Coverage must contain application lines and branches.'
}
$lineCoverage = 100.0 * [int]$coverage.'lines-covered' / [int]$coverage.'lines-valid'
$branchCoverage = 100.0 * [int]$coverage.'branches-covered' / [int]$coverage.'branches-valid'
$passed = $lineCoverage -gt $MinimumCoverage -and $branchCoverage -gt $MinimumCoverage
$status = if ($passed) { 'PASS' } else { 'FAIL' }

$rows = foreach ($class in $coverage.packages.package.classes.class) {
    $name = [System.Net.WebUtility]::HtmlEncode([string]$class.name)
    $lines = [math]::Round(100.0 * [double]$class.'line-rate', 2)
    $branches = [math]::Round(100.0 * [double]$class.'branch-rate', 2)
    $missed = @($class.lines.line | Where-Object { [int]$_.hits -eq 0 } | ForEach-Object { $_.number }) -join ', '
    "<tr><td>$name</td><td>$lines%</td><td>$branches%</td><td>$missed</td></tr>"
}
$xmlLink = [System.Net.WebUtility]::HtmlEncode([System.IO.Path]::GetRelativePath($resultDirectory, $reports[0].FullName).Replace('\', '/'))
$lineText = $lineCoverage.ToString('F2', [cultureinfo]::InvariantCulture)
$branchText = $branchCoverage.ToString('F2', [cultureinfo]::InvariantCulture)
$html = @"
<!doctype html>
<html lang="en"><meta charset="utf-8"><title>Snake unit test coverage</title>
<style>
body { font: 16px system-ui; max-width: 1050px; margin: 3rem auto; padding: 0 1rem; color: #18232d; }
table { border-collapse: collapse; width: 100%; } th, td { text-align: left; padding: .7rem; border-bottom: 1px solid #ddd; }
.status { font-size: 1.5rem; font-weight: bold; } a { color: #145b9d; }
</style>
<h1>Snake unit test coverage</h1>
<p class="status">$status — Lines: $lineText% · Branches: $branchText%</p>
<p>Both measurements must be strictly greater than $MinimumCoverage%.</p>
<p>All C# application files are included, including Program and ConsoleTerminal.
Test code and dependency assemblies are outside the application measurement.</p>
<table><thead><tr><th>Class</th><th>Lines</th><th>Branches</th><th>Uncovered source lines</th></tr></thead>
<tbody>$($rows -join [Environment]::NewLine)</tbody></table>
<p>The real terminal adapter and executable entry point are exercised by the separate E2E suite.
Those runs are not added to this unit-test coverage percentage.</p>
<p><a href="$xmlLink">Raw Cobertura coverage</a> · <a href="unit-tests.trx">Test results</a></p>
</html>
"@
$htmlPath = Join-Path $resultDirectory 'coverage.html'
Set-Content -LiteralPath $htmlPath -Value $html -Encoding utf8
$latestLink = [System.IO.Path]::GetRelativePath((Join-Path $PSScriptRoot 'TestResults'), $htmlPath).Replace('\', '/')
Set-Content -LiteralPath (Join-Path $PSScriptRoot 'TestResults/latest.html') -Encoding utf8 -Value `
    "<!doctype html><meta charset='utf-8'><meta http-equiv='refresh' content='0;url=$latestLink'><a href='$latestLink'>Latest coverage report</a>"
# Keep a plain summary with the unique report's location for command-line readers.
$summary = "$status - Line coverage: $lineText%; branch coverage: $branchText%. Required: > $MinimumCoverage%."
Write-Host $summary
Write-Host "Report: $htmlPath"
Set-Content -LiteralPath (Join-Path $PSScriptRoot 'TestResults/latest.txt') -Value "$summary`n$htmlPath"
if (-not $passed) {
    throw 'Application coverage is below the required threshold.'
}
