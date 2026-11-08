; Inno Setup 7 script for Cognia: task installer, after task build.
; It packs desktop/dist/Cognia/ into one file in desktop/dist/.

#define AppVersion "0.1.0-alpha"

[Setup]
; Windows finds an earlier install by this id, so it never changes.
AppId={{E7D64AA5-892D-4A81-941D-89821C1B93BE}
AppName=Cognia
AppVersion={#AppVersion}
; Windows file versions take numbers only.
VersionInfoVersion=0.1.0.0
SetupArchitecture=x64
; Installs for the current user, so no administrator rights are needed.
PrivilegesRequired=lowest
DefaultDirName={autopf}\Cognia
DefaultGroupName=Cognia
DisableProgramGroupPage=yes
WizardStyle=modern dynamic
SetupIconFile=..\src\resources\logo.ico
UninstallDisplayIcon={app}\Cognia.exe
Compression=lzma2
SolidCompression=yes
; One installer and nothing beside it.
DiskSpanning=no
OutputDir=..\dist
OutputBaseFilename=Cognia-{#AppVersion}-setup

[Tasks]
Name: "startup"; Description: "Start Cognia with Windows"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\Cognia\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Cognia"; Filename: "{app}\Cognia.exe"
Name: "{autodesktop}\Cognia"; Filename: "{app}\Cognia.exe"; Tasks: desktopicon

[Registry]
; The same line that the switch in the application writes.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Cognia"; ValueData: """{app}\Cognia.exe"" --background"; Tasks: startup

[Run]
Filename: "{app}\Cognia.exe"; Description: "{cm:LaunchProgram,Cognia}"; Flags: nowait postinstall skipifsilent

[Code]
const
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // The user may have turned the switch on after the install.
    RegDeleteValue(HKEY_CURRENT_USER, RunKey, 'Cognia');
    // A silent uninstall takes the default answer, which deletes.
    if SuppressibleMsgBox(
      'Also delete your conversations, memories and characters?' #13#13 +
      ExpandConstant('{localappdata}\Cognia') + #13#13 +
      'This cannot be undone.',
      mbConfirmation, MB_YESNO, IDYES) = IDYES then
      DelTree(ExpandConstant('{localappdata}\Cognia'), True, True, True);
  end;
end;
