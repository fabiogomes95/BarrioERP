' Roda publicar_cardapio.ps1 sem abrir janela (usado pela tarefa agendada
' "BarrioERP-Publicar-Cardapio" — powershell -WindowStyle Hidden ainda pisca).
CreateObject("WScript.Shell").Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""D:\Users\Fabinho\Documents\BarrioERP\deploy\windows\publicar_cardapio.ps1""", 0, False
