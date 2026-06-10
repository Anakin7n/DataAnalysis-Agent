Set ws = CreateObject("WScript.Shell")
ws.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
ws.Run "powershell -NoExit -ExecutionPolicy Bypass -File ""start.ps1""", 1, False
