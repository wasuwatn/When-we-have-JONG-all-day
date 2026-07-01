; Inno Setup script for the SMD NXT Agent GUI.
;
; Builds a single click-through Windows installer (Setup.exe) that:
;   - installs the PyInstaller-built smd-nxt-gui.exe plus config\ and
;     examples\ next to it
;   - needs no admin rights (installs under the current user's
;     %LOCALAPPDATA%, not Program Files)
;   - adds a Start Menu entry and optional desktop shortcut
;   - can launch the app immediately after install finishes
;
; Built by .github/workflows/build-windows-installer.yml on windows-latest,
; via `iscc installer\smd-nxt-agent.iss` (run from the repo root, so the
; relative Source: paths below resolve against dist\, config\, examples\).

#define MyAppName "SMD NXT Agent"
#define MyAppVersion "0.1.0"
#define MyAppExeName "smd-nxt-gui.exe"

[Setup]
AppId={{6B6E9B7B-2C7F-4B58-9C3E-6E6D6F6E6B7A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\SmdNxtAgent
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableWelcomePage=no
DisableDirPage=no
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=installer_output
OutputBaseFilename=SmdNxtAgent-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config\*"; DestDir: "{app}\config"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\examples\*.pdf"; DestDir: "{app}\examples"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
