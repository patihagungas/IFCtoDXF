; installer.iss
; ─────────────────────────────────────────────────────────────────────────────
; Inno Setup 6 script — IFC → DXF Converter
;
; Prerequisites:
;   1. Build the app first:  pyinstaller ifc2dxf.spec
;   2. Open this file in Inno Setup Compiler (https://jrsoftware.org/isinfo.php)
;   3. Press Compile (Ctrl+F9) → produces Output\IFC2DXF_Setup.exe
; ─────────────────────────────────────────────────────────────────────────────

#define AppName      "IFC2DXF Converter"
#define AppVersion   "1.0.0"
#define AppPublisher "Your Company Name"
#define AppURL       "https://yourwebsite.com"
#define AppExeName   "IFC2DXF.exe"
; Path to the PyInstaller output directory (relative to this .iss file)
#define DistDir      "dist\IFC2DXF"

[Setup]
; ── Identity ──────────────────────────────────────────────────────────────
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}

; ── Install location ───────────────────────────────────────────────────────
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

; ── Output installer file ──────────────────────────────────────────────────
OutputDir=Output
OutputBaseFilename=IFC2DXF_Setup_v{#AppVersion}
SetupIconFile=assets\icon.ico      ; Remove this line if you have no icon
Compression=lzma2/ultra64
SolidCompression=yes

; ── Appearance ────────────────────────────────────────────────────────────
WizardStyle=modern
; WizardImageFile=assets\wizard_banner.bmp   ; 164x314 px (optional)
; WizardSmallImageFile=assets\wizard_logo.bmp ; 55x55 px  (optional)

; ── Privileges ────────────────────────────────────────────────────────────
PrivilegesRequiredOverridesAllowed=dialog
PrivilegesRequired=lowest           ; Does NOT require admin (installs per-user)

; ── Misc ──────────────────────────────────────────────────────────────────
ShowLanguageDialog=no
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";    Description: "Create a &Desktop shortcut";       GroupDescription: "Additional icons:"; Flags: unchecked
Name: "quicklaunchicon"; Description: "Create a &Quick Launch shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
; Copy the entire PyInstaller output folder
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu shortcut
Name: "{group}\{#AppName}";                Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}";      Filename: "{uninstallexe}"

; Desktop shortcut (optional task)
Name: "{autodesktop}\{#AppName}";          Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

; Quick Launch shortcut (optional task, Windows XP/Vista only)
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: quicklaunchicon

[Run]
; Offer to launch the app after installation
Filename: "{app}\{#AppExeName}"; \
    Description: "Launch {#AppName}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up any output DXF files left in the install folder (if any)
Type: filesandordirs; Name: "{app}"

[Code]
// Optional: Prevent installing on 32-bit Windows
function InitializeSetup(): Boolean;
begin
  if not Is64BitInstallMode then begin
    MsgBox('This application requires a 64-bit version of Windows.', mbError, MB_OK);
    Result := False;
  end else
    Result := True;
end;
