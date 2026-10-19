@echo off
rem Переключаем консоль на UTF-8, чтобы русский текст bat и Python выводился без кракозябр.
chcp 65001 >nul
rem Запуск приложения визуализации графа зависимостей.
rem Без аргументов показываем подсказку (пример команды).
if "%~1"=="" (
    echo Использование:
    echo run.bat --package A --version 1.0.0 --test-mode --test-repo tests\fixtures\repo_basic.txt --output out\basic.png --load-order
    pause
    exit /b 1
)
python src\main.py %*
pause
