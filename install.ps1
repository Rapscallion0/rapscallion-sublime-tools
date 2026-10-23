<#
.SYNOPSIS
    Installs Rapscallion Tools packages into Sublime Text 4.

.DESCRIPTION
    Automates the installation, linking (NTFS directory junctions), and uninstallation
    of the Rapscallion Tools package suite for Sublime Text on Windows.

.PARAMETER All
    Installs all available packages in the repository.

.PARAMETER Packages
    One or more package names to install (e.g. -Packages RapscallionBookmarks,RapscallionSILTools).

.PARAMETER Mode
    Installation mode:
    - 'Junction' (Default): Creates live NTFS directory junctions (mklink /J). Edits in the repository reflect immediately in Sublime Text.
    - 'Copy': Copies clean package files into Sublime Text (independent of the repository).

.PARAMETER Uninstall
    Uninstalls the specified packages (or all packages if -All is passed).

.PARAMETER SublimePackagesPath
    Custom path to Sublime Text Packages directory (defaults to %APPDATA%\Sublime Text\Packages).

.EXAMPLE
    .\install.ps1
    Opens the interactive package selection menu.

.EXAMPLE
    .\install.ps1 -All
    Links all packages into Sublime Text using live directory junctions.

.EXAMPLE
    .\install.ps1 -Packages RapscallionBookmarks,RapscallionNotes -Mode Copy
    Copies only the Bookmarks and Notes packages to Sublime Text.

.EXAMPLE
    .\install.ps1 -All -Uninstall
    Removes all Rapscallion package links/folders from Sublime Text.
#>

[CmdletBinding()]
param(
    [switch]$All,
    [string[]]$Packages,
    [ValidateSet("Junction", "Copy")]
    [string]$Mode = "Junction",
    [switch]$Uninstall,
    [string]$SublimePackagesPath
)

$ErrorActionPreference = "Stop"

# ==============================================================================
# Discovery & Environment Setup
# ==============================================================================

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Default Sublime Text packages path
if (-not $SublimePackagesPath) {
    $SublimePackagesPath = Join-Path $env:APPDATA "Sublime Text\Packages"
}

# Discover all packages containing a .sublime-* config or README
$AvailablePackages = Get-ChildItem -Path $ScriptDir -Directory | Where-Object {
    $_.Name -like "Rapscallion*" -and (Test-Path (Join-Path $_.FullName "README.md"))
} | Select-Object -ExpandProperty Name | Sort-Object

if ($AvailablePackages.Count -eq 0) {
    Write-Error "No Rapscallion packages found in '$ScriptDir'."
    exit 1
}

# Ensure destination directory exists if installing
if (-not $Uninstall -and -not (Test-Path $SublimePackagesPath)) {
    Write-Host "[*] Creating Sublime Text Packages folder: $SublimePackagesPath" -ForegroundColor Cyan
    New-Item -ItemType Directory -Path $SublimePackagesPath -Force | Out-Null
}

# ==============================================================================
# Interactive Menu (if no CLI flags provided)
# ==============================================================================

if (-not $All -and (-not $Packages -or $Packages.Count -eq 0) -and -not $Uninstall) {
    Clear-Host
    Write-Host "================================================================================" -ForegroundColor Cyan
    Write-Host "         Rapscallion Tools Suite - Package Installer for Sublime Text 4         " -ForegroundColor Yellow
    Write-Host "================================================================================" -ForegroundColor Cyan
    Write-Host " Target Sublime Path: $SublimePackagesPath" -ForegroundColor Gray
    Write-Host ""
    Write-Host " Available Packages:" -ForegroundColor White
    for ($i = 0; $i -lt $AvailablePackages.Count; $i++) {
        $pkgName = $AvailablePackages[$i]
        $installedPath = Join-Path $SublimePackagesPath $pkgName
        $status = "Not Installed"
        $statusColor = "DarkGray"

        if (Test-Path $installedPath) {
            $item = Get-Item $installedPath -Force
            if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                $status = "Linked (Junction)"
                $statusColor = "Green"
            } else {
                $status = "Installed (Copy)"
                $statusColor = "Green"
            }
        }

        Write-Host ("  [{0}] {1,-24} - " -f ($i + 1), $pkgName) -NoNewline
        Write-Host $status -ForegroundColor $statusColor
    }

    Write-Host ""
    Write-Host " Options:" -ForegroundColor White
    Write-Host "  Enter numbers to install (e.g. '1,3,5')" -ForegroundColor Gray
    Write-Host "  Type 'A' to install All packages" -ForegroundColor Gray
    Write-Host "  Type 'U' to Uninstall packages" -ForegroundColor Gray
    Write-Host "  Type 'Q' to Quit" -ForegroundColor Gray
    Write-Host ""

    $choice = (Read-Host " Select an option").Trim()

    if ($choice -match '^(?i)q$') {
        Write-Host "Operation cancelled." -ForegroundColor Yellow
        exit 0
    }

    if ($choice -match '^(?i)u$') {
        $Uninstall = $true
        $uninstChoice = Read-Host "Uninstall (A)ll or specific package numbers? [A/1,2...]"
        if ($uninstChoice -match '^(?i)a$') {
            $SelectedPackages = $AvailablePackages
        } else {
            $indices = $uninstChoice -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]$_ - 1 }
            $SelectedPackages = @()
            foreach ($idx in $indices) {
                if ($idx -ge 0 -and $idx -lt $AvailablePackages.Count) {
                    $SelectedPackages += $AvailablePackages[$idx]
                }
            }
        }
    } elseif ($choice -match '^(?i)a$') {
        $SelectedPackages = $AvailablePackages
    } else {
        $indices = $choice -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]$_ - 1 }
        $SelectedPackages = @()
        foreach ($idx in $indices) {
            if ($idx -ge 0 -and $idx -lt $AvailablePackages.Count) {
                $SelectedPackages += $AvailablePackages[$idx]
            }
        }
    }

    if (-not $Uninstall) {
        Write-Host ""
        Write-Host " Select Installation Mode:" -ForegroundColor White
        Write-Host "  [1] Junction (Recommended) - Edits in this repo sync live with Sublime Text" -ForegroundColor Gray
        Write-Host "  [2] Copy - Copies clean folders independently into Sublime Text" -ForegroundColor Gray
        $modeChoice = Read-Host " Choose mode [1/2] (Default: 1)"
        if ($modeChoice.Trim() -eq "2") {
            $Mode = "Copy"
        } else {
            $Mode = "Junction"
        }
    }
} else {
    if ($All) {
        $SelectedPackages = $AvailablePackages
    } else {
        $SelectedPackages = @()
        foreach ($p in $Packages) {
            $match = $AvailablePackages | Where-Object { $_ -like "*$p*" }
            if ($match) {
                $SelectedPackages += $match
            } else {
                Write-Warning "Package '$p' not found. Skipping."
            }
        }
    }
}

if (-not $SelectedPackages -or $SelectedPackages.Count -eq 0) {
    Write-Warning "No valid packages selected."
    exit 0
}

# ==============================================================================
# Execute Installation or Uninstallation
# ==============================================================================

Write-Host ""
Write-Host "================================================================================" -ForegroundColor Cyan
if ($Uninstall) {
    Write-Host " Uninstalling $( $SelectedPackages.Count ) package(s)..." -ForegroundColor Yellow
} else {
    Write-Host " Installing $( $SelectedPackages.Count ) package(s) via $Mode mode..." -ForegroundColor Green
}
Write-Host " Target Directory: $SublimePackagesPath" -ForegroundColor Gray
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host ""

$SuccessCount = 0
$FailCount = 0

foreach ($pkg in $SelectedPackages) {
    $sourcePath = Join-Path $ScriptDir $pkg
    $targetPath = Join-Path $SublimePackagesPath $pkg

    if ($Uninstall) {
        try {
            if (Test-Path $targetPath) {
                $item = Get-Item $targetPath -Force
                if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                    # Reparse point (Junction/Symlink): remove via cmd rmdir to avoid deleting target contents
                    cmd /c rmdir "$targetPath"
                } else {
                    Remove-Item -Path $targetPath -Recurse -Force
                }
                Write-Host " [x] Uninstalled: $pkg" -ForegroundColor Yellow
                $SuccessCount++
            } else {
                Write-Host " [-] Not present: $pkg" -ForegroundColor DarkGray
            }
        } catch {
            Write-Host " [!] Error removing ${pkg}: $_" -ForegroundColor Red
            $FailCount++
        }
        continue
    }

    # Installing package
    try {
        # If target already exists, remove it cleanly first
        if (Test-Path $targetPath) {
            $existing = Get-Item $targetPath -Force
            if ($existing.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                cmd /c rmdir "$targetPath"
            } else {
                Remove-Item -Path $targetPath -Recurse -Force
            }
        }

        if ($Mode -eq "Junction") {
            # Create NTFS Directory Junction (mklink /J)
            $linkResult = cmd /c mklink /J "$targetPath" "$sourcePath"
            if (Test-Path $targetPath) {
                Write-Host " [+] Linked: $pkg" -ForegroundColor Green
                Write-Host "     -> $targetPath" -ForegroundColor DarkGray
                $SuccessCount++
            } else {
                throw "Failed to create junction. $linkResult"
            }
        } else {
            # Copy Mode: Copy directory excluding git & pycache
            New-Item -ItemType Directory -Path $targetPath -Force | Out-Null
            Get-ChildItem -Path $sourcePath -Recurse | Where-Object {
                $_.FullName -notmatch '\\__pycache__' -and
                $_.Extension -ne '.pyc' -and
                $_.Name -ne '.git'
            } | ForEach-Object {
                $rel = $_.FullName.Substring($sourcePath.Length + 1)
                $dest = Join-Path $targetPath $rel
                if ($_.PSIsContainer) {
                    New-Item -ItemType Directory -Path $dest -Force | Out-Null
                } else {
                    Copy-Item -Path $_.FullName -Destination $dest -Force
                }
            }
            Write-Host " [+] Copied: $pkg" -ForegroundColor Green
            Write-Host "     -> $targetPath" -ForegroundColor DarkGray
            $SuccessCount++
        }
    } catch {
        Write-Host " [!] Error installing ${pkg}: $_" -ForegroundColor Red
        $FailCount++
    }
}

Write-Host ""
Write-Host "--------------------------------------------------------------------------------" -ForegroundColor Gray
if ($Uninstall) {
    Write-Host " Uninstallation completed: $SuccessCount removed, $FailCount errors." -ForegroundColor Yellow
} else {
    Write-Host " Installation completed: $SuccessCount succeeded, $FailCount failed." -ForegroundColor Green
    Write-Host " Sublime Text 4 will automatically recognize the changes without restarting." -ForegroundColor Cyan
}
Write-Host "--------------------------------------------------------------------------------" -ForegroundColor Gray
Write-Host ""
