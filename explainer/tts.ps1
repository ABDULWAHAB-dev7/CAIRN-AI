# Text to speech with the voices built into Windows (WinRT). No download, no account.
#   powershell -NoProfile -File tts.ps1 -Jobs jobs.json -Voice Ravi [-List]
# jobs.json: [{"text": "...", "out": "C:\\path\\line.wav"}, ...]
param([string]$Jobs = "", [string]$Voice = "Ravi", [double]$Rate = 1.0, [switch]$List)

Add-Type -AssemblyName System.Runtime.WindowsRuntime
[void][Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime]
[void][Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType = WindowsRuntime]

if ($List) {
    [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | ForEach-Object { "{0} | {1}" -f $_.DisplayName, $_.Language }
    exit 0
}

$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) {
    $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); [void]$t.Wait(-1); $t.Result
}

$synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
$v = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | Where-Object { $_.DisplayName -match $Voice } | Select-Object -First 1
if (-not $v) { Write-Error "voice '$Voice' not found"; exit 2 }
$synth.Voice = $v
$synth.Options.SpeakingRate = $Rate

foreach ($job in (Get-Content -Raw -Encoding UTF8 $Jobs | ConvertFrom-Json)) {
    $stream = Await ($synth.SynthesizeTextToStreamAsync($job.text)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
    $reader = New-Object Windows.Storage.Streams.DataReader($stream)
    [void](Await ($reader.LoadAsync([uint32]$stream.Size)) ([uint32]))
    $bytes = New-Object byte[] $stream.Size
    $reader.ReadBytes($bytes)
    [System.IO.File]::WriteAllBytes($job.out, $bytes)
    $reader.Dispose(); $stream.Dispose()
}
"done"
