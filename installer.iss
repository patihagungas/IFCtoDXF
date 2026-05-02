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
#define AppVersion   "1.0.2"
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
AppComments=Convert IFC building models into AutoCAD-ready DXF files. Supports all structural, architectural, and MEP elements with 3D preview and batch export.

; ── Install location ───────────────────────────────────────────────────────
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

; ── Output installer file ──────────────────────────────────────────────────
OutputDir=Output
OutputBaseFilename=IFC2DXF_Setup_v{#AppVersion}
SetupIconFile=P.ico
Compression=lzma2/ultra64
SolidCompression=yes

; ── Appearance ────────────────────────────────────────────────────────────
WizardStyle=modern
WizardImageFile=wizard_banner.bmp
WizardSmallImageFile=wizard_logo.bmp

; ── Privileges ────────────────────────────────────────────────────────────
PrivilegesRequiredOverridesAllowed=dialog
PrivilegesRequired=lowest

; ── Misc ──────────────────────────────────────────────────────────────────
DisableWelcomePage=no
ShowLanguageDialog=no
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
; ── Welcome page ──────────────────────────────────────────────────────────
WelcomeLabel1=Welcome to {#AppName} Setup
WelcomeLabel2=What is {#AppName}?%n{#AppName} converts IFC building models into DXF files for use in AutoCAD and other CAD software.%n%n--------------------------------------------------%nThis Software was Made by Path.%nIf you got this Software from someone else - screw it.%nThis software is for our people to make the job easier.%nScrew your boss and everyone who keeps forcing the impossible job on us. F em.%n%n- P.s Have fun and Enjoy the work.%n--------------------------------------------------

; ── Ready to install page ─────────────────────────────────────────────────
ReadyLabel1=Ready to Install
ReadyLabel2a=Setup is ready to install {#AppName} on your computer.
ReadyLabel2b=Click Install to proceed, or click Back to review or change any settings.

; ── Installing page ───────────────────────────────────────────────────────
InstallingLabel=Please wait while Setup installs {#AppName} on your computer...

; ── Finish page ───────────────────────────────────────────────────────────
FinishedHeadingLabel=Completing {#AppName} Setup
FinishedLabel=Setup has successfully installed {#AppName} on your computer.%n%nYou can now convert IFC files to DXF from the Start Menu or Desktop shortcut.%n%nGood Luck and Have Fun as Usual.

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
