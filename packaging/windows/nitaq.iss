; Nitaq desktop app installer (Inno Setup 6). Built by .github/workflows/desktop.yml:
;   iscc /DAppVersion=1.1.0 packaging\windows\nitaq.iss
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6E2B9C47-3A1F-4D58-9B0E-2C7A5F1D8E34}
AppName=Nitaq
AppVersion={#AppVersion}
AppVerName=Nitaq {#AppVersion}
AppPublisher=Mohamed Ahmed (fernata-dev)
AppPublisherURL=https://byhamo.bond
AppSupportURL=https://github.com/fernata-dev/Nitaq/issues
AppUpdatesURL=https://github.com/fernata-dev/Nitaq/releases/latest
DefaultDirName={autopf}\Nitaq
DefaultGroupName=Nitaq
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\out
OutputBaseFilename=Nitaq-Setup-Windows-x64
SetupIconFile=..\icons\nitaq.ico
UninstallDisplayIcon={app}\Nitaq.exe
UninstallDisplayName=Nitaq
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\Nitaq.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Nitaq"; Filename: "{app}\Nitaq.exe"; Comment: "Stops AI agents from acting on hidden instructions"
Name: "{autodesktop}\Nitaq"; Filename: "{app}\Nitaq.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Nitaq.exe"; Description: "{cm:LaunchProgram,Nitaq}"; Flags: nowait postinstall skipifsilent
