Set FSO = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")

' Obtiene la ruta del directorio donde se encuentra este script
ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)

' Establece el directorio de trabajo actual
WshShell.CurrentDirectory = ScriptDir

' Ejecuta el descargador en bucle continuo cada 10 minutos (600 segundos) de forma 100% invisible
WshShell.Run "cmd /c python totvs_downloader.py --headless --loop --interval 600", 0, False
