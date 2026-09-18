param(
    [switch]$ValidateOnly,
    [string]$ConfigPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class HaishinJobObject
{
    [StructLayout(LayoutKind.Sequential)]
    public struct JOBOBJECT_BASIC_LIMIT_INFORMATION
    {
        public long PerProcessUserTimeLimit;
        public long PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize;
        public UIntPtr MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass;
        public uint SchedulingClass;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct IO_COUNTERS
    {
        public ulong ReadOperationCount;
        public ulong WriteOperationCount;
        public ulong OtherOperationCount;
        public ulong ReadTransferCount;
        public ulong WriteTransferCount;
        public ulong OtherTransferCount;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    {
        public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
        public IO_COUNTERS IoInfo;
        public UIntPtr ProcessMemoryLimit;
        public UIntPtr JobMemoryLimit;
        public UIntPtr PeakProcessMemoryUsed;
        public UIntPtr PeakJobMemoryUsed;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern IntPtr CreateJobObject(IntPtr lpJobAttributes, string lpName);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetInformationJobObject(
        IntPtr hJob,
        int JobObjectInfoClass,
        IntPtr lpJobObjectInfo,
        uint cbJobObjectInfoLength);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool AssignProcessToJobObject(IntPtr hJob, IntPtr hProcess);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool CloseHandle(IntPtr hObject);
}
'@

$jobObjectExtendedLimitInformation = 9
$jobObjectLimitKillOnJobClose = 0x00002000
$jobHandle = [IntPtr]::Zero
$managedProcesses = New-Object 'System.Collections.Generic.List[System.Diagnostics.Process]'

$appDir = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $ConfigPath = Join-Path $appDir 'config.json'
}
elseif (-not [IO.Path]::IsPathRooted($ConfigPath)) {
    $ConfigPath = Join-Path $appDir $ConfigPath
}
$ConfigPath = [IO.Path]::GetFullPath($ConfigPath)

if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "Launcher config was not found: $ConfigPath. Run setup.bat first."
}

$config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json

function Get-RequiredConfigValue {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Section,

        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [string]$DisplayName
    )

    $property = $Section.PSObject.Properties[$Name]
    $value = if ($null -eq $property) { '' } else { [string]$property.Value }
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Launcher config value is missing: $DisplayName"
    }
    return $value
}

function Resolve-ConfiguredPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $expandedPath = [Environment]::ExpandEnvironmentVariables($Path)
    if ([IO.Path]::IsPathRooted($expandedPath)) {
        return [IO.Path]::GetFullPath($expandedPath)
    }
    return [IO.Path]::GetFullPath((Join-Path $appDir $expandedPath))
}

$features = $config.features
$apps = $config.apps
$launchOneComme = [bool]$features.launch_onecomme
$launchTanuEsa = [bool]$features.launch_tanuesa
$launchObs = [bool]$features.launch_obs

$obsExe = $null
$obsDir = $null
$obsProfile = $null
if ($launchObs) {
    $obsExe = Resolve-ConfiguredPath (Get-RequiredConfigValue -Section $apps -Name 'obs_exe' -DisplayName 'apps.obs_exe')
    $obsDir = Split-Path -Parent $obsExe
    $obsProfile = Get-RequiredConfigValue -Section $apps -Name 'obs_profile' -DisplayName 'apps.obs_profile'
}

$oneCommeExe = $null
if ($launchOneComme) {
    $oneCommeExe = Resolve-ConfiguredPath (Get-RequiredConfigValue -Section $apps -Name 'onecomme_exe' -DisplayName 'apps.onecomme_exe')
}

$tanuEsaExe = $null
$tanuEsaDir = $null
if ($launchTanuEsa) {
    $tanuEsaExe = Resolve-ConfiguredPath (Get-RequiredConfigValue -Section $apps -Name 'tanuesa_exe' -DisplayName 'apps.tanuesa_exe')
    $tanuEsaDir = Split-Path -Parent $tanuEsaExe
}

$translationPython = Join-Path $appDir '.venv-translation\Scripts\python.exe'
$translationServer = Join-Path $appDir 'translation_server.py'

function New-KillOnCloseJob {
    $handle = [HaishinJobObject]::CreateJobObject([IntPtr]::Zero, $null)
    if ($handle -eq [IntPtr]::Zero) {
        $errorCode = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
        throw "CreateJobObject failed. Win32 error: $errorCode"
    }

    $basicInfo = New-Object 'HaishinJobObject+JOBOBJECT_BASIC_LIMIT_INFORMATION'
    $basicInfo.LimitFlags = $jobObjectLimitKillOnJobClose

    $extendedInfo = New-Object 'HaishinJobObject+JOBOBJECT_EXTENDED_LIMIT_INFORMATION'
    $extendedInfo.BasicLimitInformation = $basicInfo

    $infoLength = [Runtime.InteropServices.Marshal]::SizeOf($extendedInfo)
    $infoPointer = [Runtime.InteropServices.Marshal]::AllocHGlobal($infoLength)

    try {
        [Runtime.InteropServices.Marshal]::StructureToPtr($extendedInfo, $infoPointer, $false)
        $configured = [HaishinJobObject]::SetInformationJobObject(
            $handle,
            $jobObjectExtendedLimitInformation,
            $infoPointer,
            $infoLength)

        if (-not $configured) {
            $errorCode = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
            [void][HaishinJobObject]::CloseHandle($handle)
            throw "SetInformationJobObject failed. Win32 error: $errorCode"
        }
    }
    finally {
        [Runtime.InteropServices.Marshal]::FreeHGlobal($infoPointer)
    }

    return $handle
}

function Test-LaunchFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        Write-Host "[OK] $Name : $Path"
        return $true
    }

    Write-Warning "$Name was not found: $Path"
    return $false
}

function Start-ManagedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,

        [string[]]$ArgumentList = @()
    )

    if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
        Write-Warning "$Name was not found: $FilePath"
        return
    }

    $startParameters = @{
        FilePath = $FilePath
        WorkingDirectory = $WorkingDirectory
        PassThru = $true
    }

    if ($ArgumentList.Count -gt 0) {
        $startParameters.ArgumentList = $ArgumentList
    }

    $process = Start-Process @startParameters

    try {
        if ($process.HasExited) {
            Write-Warning "$Name exited before it could be managed. A pre-existing single-instance app is left untouched."
            return
        }

        if (-not [HaishinJobObject]::AssignProcessToJobObject($script:jobHandle, $process.Handle)) {
            $errorCode = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
            try {
                $process.Kill()
            }
            catch {
                Write-Warning "Failed to stop unmanaged process $($process.Id): $($_.Exception.Message)"
            }
            throw "AssignProcessToJobObject failed for $Name. Win32 error: $errorCode"
        }

        $script:managedProcesses.Add($process)
        Write-Host "[STARTED] $Name (PID $($process.Id))"
    }
    catch {
        $process.Dispose()
        throw
    }
}

try {
    $jobHandle = New-KillOnCloseJob

    if ($ValidateOnly) {
        $allFound = $true
        if ($launchOneComme) {
            $allFound = (Test-LaunchFile -Name 'OneComme' -Path $oneCommeExe) -and $allFound
        }
        if ($launchTanuEsa) {
            $allFound = (Test-LaunchFile -Name 'TanuEsa3' -Path $tanuEsaExe) -and $allFound
        }
        if ($launchObs) {
            $allFound = (Test-LaunchFile -Name 'OBS Studio' -Path $obsExe) -and $allFound
        }
        $allFound = (Test-LaunchFile -Name 'Translation Python' -Path $translationPython) -and $allFound
        $allFound = (Test-LaunchFile -Name 'Translation server' -Path $translationServer) -and $allFound

        if (-not $allFound) {
            throw 'One or more launch files are missing.'
        }

        Write-Host '[VALID] Launcher syntax, paths, and Windows Job Object initialization succeeded.'
        return
    }

    if ($launchOneComme) {
        Start-ManagedProcess -Name 'OneComme' -FilePath $oneCommeExe -WorkingDirectory (Split-Path -Parent $oneCommeExe)
        Start-Sleep -Seconds 2
    }

    if ($launchTanuEsa) {
        Start-ManagedProcess -Name 'TanuEsa3' -FilePath $tanuEsaExe -WorkingDirectory $tanuEsaDir
    }
    Start-ManagedProcess -Name 'Translation Server' -FilePath $translationPython -WorkingDirectory $appDir -ArgumentList @($translationServer)
    if ($launchObs) {
        Start-Sleep -Seconds 2
        Start-ManagedProcess -Name 'OBS Studio' -FilePath $obsExe -WorkingDirectory $obsDir -ArgumentList @('--profile', $obsProfile)
    }

    Write-Host ''
    Write-Host '[RUNNING] Stop streaming in OBS, then press Ctrl+C or close this window to stop launched tools.'

    while ($true) {
        Start-Sleep -Seconds 1
    }
}
finally {
    $managedObsProcesses = @(
        $managedProcesses | Where-Object {
            try {
                (-not $_.HasExited) -and ($_.ProcessName -eq 'obs64')
            }
            catch {
                $false
            }
        }
    )

    foreach ($obsProcess in $managedObsProcesses) {
        try {
            Write-Host '[STOPPING] Asking OBS Studio to close gracefully...'
            if ($obsProcess.CloseMainWindow()) {
                if (-not $obsProcess.WaitForExit(10000)) {
                    Write-Warning 'OBS Studio did not exit within 10 seconds and will be closed with the remaining managed processes.'
                }
            }
            else {
                Write-Warning 'OBS Studio did not accept a normal window-close request and will be closed with the remaining managed processes.'
            }
        }
        catch {
            Write-Warning "Failed to request a graceful OBS Studio shutdown: $($_.Exception.Message)"
        }
    }

    if ($jobHandle -ne [IntPtr]::Zero) {
        Write-Host ''
        Write-Host '[STOPPING] Closing launched processes...'
        [void][HaishinJobObject]::CloseHandle($jobHandle)
        $jobHandle = [IntPtr]::Zero
    }

    foreach ($process in $managedProcesses) {
        $process.Dispose()
    }

    Write-Host '[STOPPED] Launcher cleanup completed.'
}
