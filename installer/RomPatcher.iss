#ifndef AppVersion
#define AppVersion "0.0.0"
#endif

#define MyAppName "RomPatcher Desktop"
#define MyAppPublisher "Marc"
#define MyAppExeName "RomPatcher.exe"
#define MyAppAssocName "RomPatcher Desktop"
#define MyAppURL "https://github.com/Balrog57/RomPatcher"

[Setup]
AppId={{4D0E9A6C-AB3C-4F19-A3A7-7AF7D4E6F5B8}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppVerName={#MyAppName} {#AppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppAssocName}
AllowNoIcons=yes
DisableProgramGroupPage=no
ArchitecturesAllowed=x64compatible
PrivilegesRequired=lowest
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
SetupIconFile=..\assets\rompatcher.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..\dist
OutputBaseFilename=RomPatcher-Setup-v{#AppVersion}-win64
VersionInfoDescription=RomPatcher Desktop Installer
ChangesAssociations=no
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
UsePreviousGroup=yes
UsePreviousTasks=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\RomPatcher.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\RomPatcher Desktop"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Check: ShouldCreateProgramGroup
Name: "{group}\Desinstaller RomPatcher Desktop"; Filename: "{uninstallexe}"; Check: ShouldCreateProgramGroup
Name: "{autodesktop}\RomPatcher Desktop"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,RomPatcher Desktop}"; Flags: nowait postinstall skipifsilent

[Code]
function ShouldCreateProgramGroup: Boolean;
begin
  Result := not WizardNoIcons;
end;
