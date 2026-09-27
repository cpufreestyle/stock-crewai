' stock-crewai scheduled run (hidden): invoked by Windows scheduled task
Set ws = CreateObject("WScript.Shell")
ws.Run """C:\Users\qm081\AppData\Local\Programs\Python\Python312\python.exe"" -u ""D:\aishare\repo\stock-crewai-master\run_crew_then_release.py""", 0, False
