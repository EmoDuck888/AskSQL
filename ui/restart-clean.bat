@echo off
echo 正在清理缓存并重启应用...

echo 1. 删除 node_modules/.cache
if exist "node_modules\.cache" (
    rmdir /s /q "node_modules\.cache"
    echo    - 已删除 node_modules/.cache
)

echo 2. 设置环境变量
set REACT_APP_API_URL=http://localhost:8065/api
set REACT_APP_HYBRID_ENABLED=true

echo 3. 显示当前环境变量
echo    REACT_APP_API_URL=%REACT_APP_API_URL%
echo    REACT_APP_HYBRID_ENABLED=%REACT_APP_HYBRID_ENABLED%

echo 4. 启动应用
npm start
