@echo off
chcp 65001 >nul
rem 상위 폴더의 최신 공공데이터 CSV로 웹지도 데이터(data\*.js)를 다시 만듭니다.
rem 노선 형상까지 새로 받으려면:  데이터갱신.bat --refresh-osm
set PYTHONIOENCODING=utf-8
set "QPY="
for /d %%D in ("C:\Program Files\QGIS*") do if exist "%%D\bin\python-qgis-ltr.bat" set "QPY=%%D\bin\python-qgis-ltr.bat"
for /d %%D in ("C:\Program Files\QGIS*") do if exist "%%D\bin\python-qgis.bat" set "QPY=%%D\bin\python-qgis.bat"
if not defined QPY (
  echo QGIS Python을 찾지 못했습니다. QGIS가 설치되어 있는지 확인하세요.
  pause
  exit /b 1
)
call "%QPY%" "%~dp0build_data.py" %*
echo.
echo 완료. data\build_report.txt 에서 매칭 실패 역을 확인하세요.
pause
