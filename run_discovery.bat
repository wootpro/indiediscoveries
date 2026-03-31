@echo off
cd /d C:\Users\Pro\Projects\IndieMusic
call .venv\Scripts\activate
echo [%date% %time%] Starting IndieMusic discovery run >> run_log.txt
python main.py >> run_log.txt 2>&1
echo [%date% %time%] Run complete (exit code: %errorlevel%) >> run_log.txt
if exist last_run_report.html start "" last_run_report.html
