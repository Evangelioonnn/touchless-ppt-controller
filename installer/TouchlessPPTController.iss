#ifndef SourceDir
  #error SourceDir must point to the complete candidate portable directory
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif

[Setup]
AppId={{9F6266D1-8C74-4D65-9F87-BF470B3E2647}
AppName=Touchless PPT Controller Beta
AppVersion=0.2.0-beta.3
AppVerName=Touchless PPT Controller 0.2.0-beta.3 (native tray candidate)
VersionInfoVersion=0.2.0.3
DefaultDirName={localappdata}\Programs\TouchlessPPTController-Beta
DefaultGroupName=Touchless PPT Controller Beta
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
LicenseFile=..\LICENSE
SetupIconFile=..\windows_launcher\TouchlessPPTController.ico
UninstallDisplayIcon={app}\TouchlessPPTController.exe
OutputDir={#OutputDir}
OutputBaseFilename=TouchlessPPTController-v0.2.0-beta.3-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no
AppMutex=Local\TouchlessPPTController.UI.v2
DisableProgramGroupPage=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Touchless PPT Controller Beta"; Filename: "{app}\TouchlessPPTController.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Touchless PPT Controller Beta"; Filename: "{app}\TouchlessPPTController.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\TouchlessPPTController.exe"; Description: "Open Touchless PPT Controller"; Flags: nowait postinstall skipifsilent

; No service, scheduled task, startup entry, security exclusion or user-data deletion.
